# Carbon Cost Module

A tool for estimating and reporting the carbon footprint and AWS cost of cloud infrastructure. Supports pre-provisioning estimates from Terraform plans, live infrastructure audits, and real AWS carbon and billing data from CCFT and Cost Explorer.

---

## Architecture

```
carbon-cost-module/
├── api/                  FastAPI backend
│   ├── routes/
│   │   ├── estimate.py   Terraform plan + live scan endpoints
│   │   ├── ccft.py       AWS Customer Carbon Footprint Tool endpoint
│   │   └── billing.py    AWS Cost Explorer endpoint
│   ├── config.py         Settings loaded from .env
│   └── main.py           App entry point, router registration
├── calculator.py         Core carbon estimation engine (CCF methodology)
├── cost_calculator.py    AWS Pricing API cost estimation
├── terraform_estimate.py Terraform plan parser and estimator
├── aws_actual.py         Live AWS infrastructure scanner
├── data/
│   ├── grid_intensity.json   Grid carbon intensity per AWS region (kgCO2e/kWh)
│   ├── wattage.json          Instance min/max wattage + PUE
│   └── embodied.json         Instance embodied carbon factors from Boavizta (kgCO2e/hour)
├── scripts/
│   └── fetch_embodied.py     Regenerates data/embodied.json from Boavizta API
└── frontend/             React + Vite frontend
    └── src/
        ├── App.jsx                 Router + nav bar + stub-data toggle
        ├── api/client.js           Axios client for backend requests
        ├── data/stubData.js        Mock results for demo mode
        ├── pages/
        │   ├── Provision.jsx       Pre-provisioning estimate form
        │   ├── LiveScan.jsx        Infrastructure audit page
        │   └── Dashboard.jsx       CCFT carbon + billing dashboard
        └── components/
            ├── ResourceForm.jsx        RJSF-based resource form
            ├── EstimateResults.jsx     Results display with per-resource breakdown
            ├── CcftComparisonChart.jsx LBM and MBM carbon charts
            └── BillingChart.jsx        Cost Explorer billing chart
```

---

## Getting Started

### Backend

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in AWS credentials in .env
uvicorn api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Use the **Use stub data** toggle in the app header to switch Dashboard and Infrastructure Audit between live AWS data and mock data. The Provision tab always uses live estimation from the uploaded Terraform plan.

---

## How the application works end to end

At a high level, the project has **one Python backend** that performs all carbon and cost calculations, and **one React frontend** that presents three user-facing workflows:

1. **Provision** — estimate a resource *before* it is created.
2. **Infrastructure Audit** — inspect resources that already exist in AWS.
3. **Dashboard** — show AWS-reported carbon actuals (CCFT) and billing actuals (Cost Explorer).

The typical request flow is:

1. A user interacts with a React page.
2. The page calls the backend with `axios` (`frontend/src/api/client.js`).
3. A FastAPI route in `api/routes/*.py` receives the request.
4. The route either:
   - calls pure estimation code (`calculator.py`, `terraform_estimate.py`), or
   - calls AWS APIs through `boto3` (`aws_actual.py`, `cost_calculator.py`, `api/routes/ccft.py`, `api/routes/billing.py`).
5. The backend returns a JSON payload shaped for the frontend UI.
6. Shared React components render totals, tables, charts, and carbon equivalencies.

### Why the architecture is split this way

- **All calculation logic lives in Python** so the same rules are used whether the request comes from Terraform-plan estimation, live AWS scanning, or tests.
- **The React app is thin**: it mostly gathers inputs, calls APIs, and renders results. That keeps the important methodology in one place.
- **The Provision tab posts a synthetic Terraform plan** instead of inventing a second API contract. This is deliberate: the same backend path can handle both a real `terraform show -json` output and a UI-generated estimate request.
- **Stub mode lives in the frontend, not the backend**. That keeps production API behaviour simple while still allowing demos without AWS credentials.

---

## Backend walkthrough (Python)

### `api/main.py` — the application entry point

This file creates the FastAPI app and wires together the rest of the backend:

- registers CORS using values from `api/config.py`
- mounts the estimate, CCFT, and billing routers under `/api`
- applies optional API-key protection through `verify_api_key`
- refreshes `data/embodied.json` on startup if the cache is stale or missing
- exposes `GET /api/health`

That startup refresh matters because embodied-carbon factors come from Boavizta and are cached locally. The app tries to keep that cache fresh without requiring a manual script run every time.

### `api/config.py` — typed settings

This is the single source of truth for environment-driven configuration:

- app environment and port
- CORS origins
- optional `API_KEY`
- embodied-data refresh settings
- AWS credential inputs (`AWS_PROFILE`, access key, secret key)

The project uses `pydantic-settings` so the rest of the code imports one shared `settings` object instead of parsing environment variables in many places.

### `api/dependencies.py` — optional API-key auth

`verify_api_key()` is attached to all routers. It behaves like this:

- if `API_KEY` is empty, auth is effectively disabled
- if `API_KEY` is set, requests must include `X-API-Key`

This is intentionally simple: enough protection for a deployed internal tool without complicating local development.

### `api/routes/estimate.py` — estimation endpoints

This file provides two workflows:

- `POST /api/estimate/plan`
  - accepts a Terraform-plan-shaped JSON document
  - passes it to `terraform_estimate.estimate_from_plan_dict()`
- `GET /api/estimate/live?region=...`
  - builds a boto3 session from settings
  - validates credentials with STS
  - calls `aws_actual.estimate_from_live()`

The helper `_build_session()` exists so credential construction is consistent across routes.

### `terraform_estimate.py` — pre-provisioning estimation

This is the core of the **Provision** flow.

Important functions:

- `extract_region_from_plan(plan)`
  Reads the provider region from Terraform JSON. If it cannot, it falls back to `eu-west-1`.
- `az_to_region(availability_zone)`
  Converts values like `eu-west-1a` to `eu-west-1`.
- `estimate_from_plan_dict(plan)`
  Walks `resource_changes`, only processes `"create"` actions, and builds the response returned to the frontend.

Supported Terraform resource types:

- `aws_instance`
- `aws_db_instance`
- `aws_ebs_volume`

Everything else is added to `skipped`.

This file also calls the cost-estimation functions in `cost_calculator.py`, so one request returns both **carbon** and **USD cost**.

### `aws_actual.py` — live AWS scanning

This is the core of the **Infrastructure Audit** flow.

It scans a single AWS region and currently models:

- running EC2 instances
- in-use EBS volumes
- available RDS instances

Why only those?

- they are the resources the calculator can currently model well
- they are easy to discover through stable AWS APIs
- they cover the main compute + storage resources most directly tied to engineering decisions

Unsupported services are not guessed. That is intentional: the tool prefers explicit scope over misleading precision.

### `calculator.py` — carbon formulas

This is the most important file for understanding the methodology.

Important functions:

- `estimate_ec2()`
  Uses min/max wattage, CPU-utilisation interpolation, PUE, and regional grid intensity.
- `estimate_ebs_storage()`
  Uses SSD/HDD storage coefficients from Cloud Carbon Footprint.
- `estimate_rds()`
  Combines compute energy and storage energy for RDS.
- `estimate_embodied()`
  Looks up embodied carbon per instance-hour from Boavizta-derived cached data.
- `reload_embodied_data()`
  Reloads the cache after startup refresh.

The result object is the `CarbonEstimate` dataclass. Every estimator returns the same structure so downstream code can aggregate results without special cases.

### `cost_calculator.py` — live AWS pricing

This file fetches **real on-demand prices** from the AWS Pricing API for:

- EC2
- EBS
- RDS

Important design choice: cost estimation is kept separate from carbon estimation. That makes the carbon formulas testable and deterministic even though pricing is an external API call.

### `api/routes/ccft.py` — AWS Customer Carbon Footprint Tool

This powers the carbon chart on the **Dashboard** tab.

It:

- calls the AWS Sustainability API in `us-east-1`
- groups monthly entries by service
- calculates totals for:
  - `total_lbm_mtco2e` / `total_mbm_mtco2e` — all services combined
  - `ec2_lbm_mtco2e` / `ec2_mbm_mtco2e` — AmazonEC2 only, for direct comparison with the Infrastructure Audit
- optionally scopes the CCFT query to a single AWS account when `AWS_CCFT_ACCOUNT_ID` is set (useful in AWS Organisations)

LBM and MBM are both returned because they answer different questions:

- **LBM** = what your workload emitted on the real grid
- **MBM** = what that looks like after AWS renewable-energy accounting

### `api/routes/billing.py` — Cost Explorer summary

This powers the billing chart on the **Dashboard** tab.

It:

- calls `ce:GetCostAndUsage`
- groups monthly cost by service
- maps verbose AWS service names into shorter labels
- excludes tax
- puts long-tail services into `Other`

That last choice keeps the chart readable. The dashboard is meant to highlight the biggest cost drivers, not every minor line item.

### `embodied_data.py` — embodied-carbon cache management

This file handles the Boavizta lookup file:

- loads cached factors from `data/embodied.json`
- fetches missing/stale data from the Boavizta API
- writes metadata such as `_source` and `_fetched_at`
- strips metadata back out when the calculator needs only numeric factors

This is why the app can start quickly most of the time while still keeping the dataset reasonably fresh.

---

## Frontend walkthrough (React)

### `frontend/src/App.jsx`

This is the top-level React component. It does three things:

1. creates the `useStubData` state
2. renders the nav bar and the global stub-data checkbox
3. maps routes to pages:
   - `/provision`
   - `/live-scan`
   - `/dashboard`

The stub toggle is held here so both the Dashboard and Infrastructure Audit pages receive the same shared state.

### `frontend/src/api/client.js`

This is a tiny shared `axios` instance. It points to:

- `VITE_API_BASE_URL` if set
- otherwise `http://localhost:8000`

Keeping API configuration in one place avoids hard-coding URLs across components.

### `frontend/src/components/ResourceForm.jsx`

This component is the heart of the **Provision** tab.

What it does:

1. picks the correct JSON schema for EC2, RDS, or EBS
2. renders the form using `@rjsf/core`
3. converts user-friendly fields into Terraform-style field names with `toAfterValues()`
4. creates a synthetic one-resource Terraform plan with `buildPlan()`
5. posts that plan to `/api/estimate/plan`
6. in parallel, posts the same resource to three low-carbon comparison regions
7. renders the shared `EstimationResults` view

This is a clever reuse of the backend: instead of building a second estimator API just for the UI, the form speaks the same “Terraform plan” language as the CLI/backend logic.

### `frontend/src/components/EstimateResults.jsx`

This component is shared by **Provision** and **Infrastructure Audit**.

It renders:

- total monthly/yearly energy
- operational carbon
- embodied carbon
- total cost
- per-resource tables split into EC2 / RDS / EBS
- skipped-resource warnings
- the optional region-comparison panel
- real-world carbon equivalencies

This shared component is why the Provision and Audit results look consistent even though they come from different backend flows.

### `frontend/src/components/CcftComparisonChart.jsx`

This component loads CCFT data and renders two charts:

- **LBM chart**
- **MBM chart**

It also:

- supports refresh
- supports stub mode
- converts metric tons to grams for consistency with the rest of the app
- shows carbon equivalencies for the latest LBM month

### `frontend/src/components/BillingChart.jsx`

This component loads billing data and renders a stacked monthly bar chart. It mirrors the CCFT chart pattern:

- initial fetch in `useEffect`
- refresh button
- loading state
- error state
- stub mode support

### `frontend/src/components/CarbonEquivalencies.jsx`

This is purely explanatory UI. It turns a carbon number into comparisons such as:

- petrol-car kilometres
- flight passenger-kilometres
- smartphone charges
- tree absorption time

It exists because raw `gCO₂e` numbers are hard for most people to interpret.

---

## How each tab works

### 1. Provision tab

Purpose: **estimate before deployment**.

Flow:

1. User selects a resource type.
2. `Provision.jsx` renders `ResourceForm`.
3. `ResourceForm` loads the matching schema:
   - `ec2.json`
   - `rds.json`
   - `ebs.json`
4. Submitted form data is transformed into Terraform-style attributes.
5. A synthetic Terraform plan is sent to `POST /api/estimate/plan`.
6. The response is rendered in `EstimationResults`.
7. Three extra requests compare the same resource against Stockholm, Paris, and New Zealand.

Why it exists: this is the engineering-decision tab. It tells you *before provisioning* what a design choice could cost in both carbon and money.

### 2. Infrastructure Audit tab

Purpose: **inspect what is already running**.

Flow:

1. User chooses one of the supported regions in the dropdown.
2. Clicking **Scan Infrastructure** either:
   - returns stub data immediately, or
   - calls `GET /api/estimate/live`
3. The backend checks AWS credentials, scans EC2/EBS/RDS, estimates carbon and price, and returns totals plus a resource list.
4. `EstimationResults` renders the same shared result view used by Provision.

Why it exists: this is the operational-review tab. It is useful for catching resources that are currently deployed, oversized, or unexpectedly expensive.

### 3. Dashboard tab

Purpose: **show AWS-reported actuals** rather than local estimates.

Flow:

1. `Dashboard.jsx` renders `CcftComparisonChart` and `BillingChart`.
2. Those components independently fetch:
   - `/api/ccft/summary`
   - `/api/billing/summary`
3. Each chart handles its own loading, refresh, and error state.
4. Stub mode swaps both components to local mock datasets.

Why it exists: this is the reporting/validation tab. Provision and Audit are model-based estimates; Dashboard shows the AWS-side actual reporting feeds that you compare yourself against.

---

## How stub mode works

Stub mode is controlled by the **Use stub data** checkbox in the app header.

### What it changes

- **Infrastructure Audit**: uses `getStubLiveScanResults(region)`
- **Dashboard**: uses `STUB_CCFT_SUMMARY` and `STUB_BILLING_SUMMARY`

### What it does not change

- **Provision** still calls the real backend

That is deliberate. Provision is fundamentally a form-to-estimator workflow and does not need AWS credentials, so there is less value in stubbing it.

### Why `getStubLiveScanResults(region)` exists

The live-scan stub clones the base dataset and swaps the selected region into every resource so the UI still reflects the user’s region choice.

### Why stubs are frontend-only

Because the goal is to demonstrate the UI and page behaviour without changing backend behaviour. This keeps the API contract honest while still supporting:

- demos
- development without AWS access
- presentations/screenshots
- chart rendering checks

---

## Why some design choices may come up in questioning

- **Why is CPU utilisation fixed at 50%?**
  Because the estimator follows the Cloud Carbon Footprint methodology for prospective estimates. Real utilisation is not available for pre-provisioning requests.

- **Why is embodied carbon only shown for EC2-class compute?**
  Because the current Boavizta-backed dataset is keyed by instance type. Equivalent high-confidence embodied datasets are not yet wired in for managed services and networking.

- **Why are only three “greenest” comparison regions shown?**
  To keep the comparison panel simple and decision-oriented. The goal is to illustrate that region choice changes operational carbon materially.

- **Why are CCFT and Billing in separate backend routes?**
  They come from different AWS services with different permissions, response shapes, and user questions.

- **Why does the dashboard use AWS data while Provision/Audit use local formulas?**
  Because the tool serves two roles: engineering estimation and actual-account reporting. Those are related but not identical problems.

---

## Configuration (.env)

```
APP_ENV=development
CORS_ALLOWED_ORIGINS=http://localhost:5173
API_KEY=                        # optional, leave empty to disable auth

AWS_DEFAULT_REGION=eu-west-1
AWS_PROFILE=                    # optional named profile
AWS_ACCESS_KEY_ID=              # leave empty to use boto3 default chain
AWS_SECRET_ACCESS_KEY=
AWS_CCFT_ACCOUNT_ID=            # optional — filter CCFT data to one account in an AWS Organisation
```

Credentials are resolved in this order:
1. `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` from `.env`
2. `AWS_PROFILE` from `.env`
3. boto3 default chain (`~/.aws/credentials`, environment variables, IAM role)

Embodied carbon data refreshes on API startup when `data/embodied.json` is missing or older than `EMBODIED_REFRESH_MAX_AGE_DAYS` (default `7`). Set `EMBODIED_REFRESH_ENABLED=false` to skip the network refresh and keep the last cached data.

---

## Carbon Estimation Methodology

### What the tool calculates

Carbon is estimated using the Cloud Carbon Footprint (CCF) methodology:

```
avg_watts = min_watts + (cpu_utilisation × (max_watts - min_watts))
energy_kwh = (avg_watts × hours / 1000) × PUE
carbon_gco2e = energy_kwh × grid_intensity × 1000
```

- **CPU utilisation** — assumed 50% (CCF default). Not pulled from CloudWatch.
- **PUE** — 1.135 (AWS published average datacenter efficiency)
- **Grid intensity** — from `data/grid_intensity.json`, sourced from CCF AWSEmissionsFactors.ts
- **Wattage** — from `data/wattage.json`, sourced from CCF aws-instances.csv / SPECpower
- **Embodied carbon** — from `data/embodied.json`, sourced from Boavizta API (`scripts/fetch_embodied.py`)

### What the tool does NOT calculate

- Embodied carbon for non-EC2 resources (for example EBS, RDS, networking)
- Networking and data transfer carbon
- Storage carbon beyond EBS (S3, EFS, etc.)
- EKS control plane carbon
- NAT gateway, load balancer, VPC endpoint carbon

---

## Data Sources

### Grid Intensity (`data/grid_intensity.json`)

Source: [CCF AWSEmissionsFactors.ts](https://github.com/cloud-carbon-footprint/cloud-carbon-footprint/blob/trunk/packages/aws/src/lib/AWSEmissionsFactors.ts)

US regions use EPA eGRID NERC region factors. EU regions use EEA emissions factors. Other regions use carbonfootprint.com country factors. Units: kgCO2e/kWh.

Notable values:
| Region | Location | kgCO2e/kWh |
|---|---|---|
| eu-north-1 | Stockholm | 0.000008 |
| eu-west-3 | Paris | 0.000074 |
| ap-southeast-6 | New Zealand | 0.00007939 |
| sa-east-1 | São Paulo | 0.00006398 |
| ca-central-1 | Canada | 0.00011541 |

The three lowest-carbon regions (Stockholm, Paris, New Zealand) are used in the region comparison panel on the Provision page.

### Wattage (`data/wattage.json`)

Source: CCF cloud-carbon-coefficients repo and SPECpower_ssj2008 data. Min watts = idle power, max watts = full load.

---

## AWS Integration

### Carbon — AWS Customer Carbon Footprint Tool (CCFT)

- Endpoint: `GET /api/ccft/summary`
- Calls `sustainability:GetCarbonFootprintSummary` via boto3
- Returns monthly LBM and MBM figures grouped by service (EC2, S3, Other)
- CCFT is only available via `us-east-1` regardless of resource region
- Data typically lags by ~3 months
- Required IAM permission: `sustainability:GetCarbonFootprintSummary`

**LBM (Location-Based Method)** — uses actual grid carbon intensity per region. Comparable to this tool's operational estimates. Use for understanding true carbon footprint and benchmarking.

**MBM (Market-Based Method)** — adjusts for AWS renewable energy certificates (RECs) and PPAs. Lower than LBM. Use for ESG reporting and sustainability disclosures.

### Cost — AWS Cost Explorer

- Endpoint: `GET /api/billing/summary`
- Calls `ce:GetCostAndUsage` via boto3
- Returns monthly unblended costs grouped by service, tax excluded
- Required IAM permission: `ce:GetCostAndUsage`

### Cost (live scan) — AWS Pricing API

- Called from `cost_calculator.py` during infrastructure audits
- Fetches real-time on-demand pricing for EC2, EBS, and RDS
- Pricing API is only available in `us-east-1` and `ap-south-1`
- Required IAM permission: `pricing:GetProducts`

---

## Infrastructure Audit Scope and Limitations

The audit (`GET /api/estimate/live`) scans:
- Running EC2 instances (state: `running`)
- In-use EBS volumes (state: `in-use`)
- Available RDS instances (state: `available`)

**It does NOT scan:**
- EKS managed node groups or Auto Mode nodes (these appear as EC2 but may not be visible depending on IAM permissions)
- Fargate tasks
- NAT gateways
- Load balancers
- VPC endpoints
- S3, DynamoDB, or other managed services
- Resources in other AWS accounts within the same organisation

**Note on EKS Auto Mode:** EKS Auto Mode nodes are provisioned as EC2 instances tagged with `aws:eks:cluster-name`. If your IAM user has EC2 describe permissions, these will appear in the audit as regular EC2 instances. The audit results explicitly note this limitation.

---

## Embodied Carbon — Research Notes

### Validation against AWS CCFT

In testing against a real AWS account at 50% CPU utilisation (the CCF methodology default), this tool produced estimates closely aligned with AWS CCFT actuals:

| Metric | This tool (estimate) | AWS CCFT (actual) |
|---|---|---|
| Carbon (EC2, 50% CPU) | 29,206.5 gCO₂e/month | ~30,000 gCO₂e/month |
| AWS Cost | ~$495/month | ~$500/month |

Both figures are within ~2% of AWS actuals, confirming the methodology is sound for EC2-scoped estimation at average utilisation.

### Embodied carbon formula (Green Software Foundation SCI spec)

```
M = TE × (TR / EL) × (RR / TR)
```

- `TE` = Total Embodied Emissions for the physical server (kgCO2e) — from Boavizta API
- `TR` = Time Reserved — hours the instance ran
- `EL` = Expected Lifespan — 4 years = 35,040 hours
- `RR` = vCPUs of the instance
- `TR` = vCPUs of the largest instance in that family

### Data source for embodied carbon

**Boavizta API** (recommended) — free, no auth, current data:
```
GET https://api.boavizta.org/v1/cloud/instance?provider=aws&instance_type=<instance_type>&verbose=false&duration=1
```
Returns `impacts.gwp.embedded.value` in kgCO2e per hour.

**CCF coefficients spreadsheet** (static snapshot):
https://docs.google.com/spreadsheets/d/1k-6JtneEu4E9pXQ9QMCXAfyntNJl8MnV2YzO4aKHh-0

### Operational vs embodied — when to use each

| Use case | Method |
|---|---|
| Comparing instance types before provisioning | Operational only |
| Comparing regions | Operational only (embodied is region-independent) |
| Right-sizing decisions | Operational only |
| ESG / GHG Protocol reporting | Operational + embodied |
| Comparing against CCFT | Operational + embodied |
| Board-level carbon reporting | Use CCFT directly |

---

## Why this tool vs CCFT

| | This tool | AWS CCFT |
|---|---|---|
| Pre-provisioning estimates | Yes | No |
| Region comparison | Yes | No |
| Real-time cost | Yes (Pricing API) | No |
| Operational carbon | Yes | Yes |
| Embodied carbon | Yes (Boavizta-based EC2 estimate) | Yes |
| Actual CPU utilisation | No (assumes 50%) | Yes (CloudWatch) |
| Full account scope | No (IAM limited) | Yes |
| ESG reporting | Not recommended | Yes |
| Engineering decisions | Yes | No |

The primary value of this tool is **pre-provisioning decision support** — helping engineers choose greener regions and right-sized instance types before they deploy. CCFT is the source of truth for actual reported carbon.

---

## Using this in another application

There are two ways to integrate carbon and cost estimation into an external project: calling the **REST API** or importing the **Python library functions** directly.

---

### Option 1 — REST API (recommended)

Start the backend as described in [Getting Started](#getting-started), then call the API from any language or tool.

#### Estimate carbon and cost from a Terraform plan

```bash
curl -s -X POST http://localhost:8000/api/estimate/plan \
  -H "Content-Type: application/json" \
  -d '{
    "configuration": {
      "provider_config": {
        "aws": { "expressions": { "region": { "constant_value": "eu-west-1" } } }
      }
    },
    "resource_changes": [
      {
        "address": "aws_instance.web",
        "type": "aws_instance",
        "change": {
          "actions": ["create"],
          "after": { "instance_type": "t3.medium" }
        }
      }
    ]
  }'
```

Response shape:

```json
{
  "resources": [
    {
      "address": "aws_instance.web",
      "resource_type": "aws_instance",
      "region": "eu-west-1",
      "carbon": {
        "energy_kwh_month": 14.1234,
        "carbon_gco2e_month": 1342.12,
        "embodied_gco2e_month": 967.44,
        "assumptions": { "cpu_utilisation": 0.5, "pue": 1.135, "..." : "..." }
      },
      "cost": {
        "cost_usd_month": 30.37,
        "pricing_details": { "hourly_price_usd": 0.0416, "hours": 730 }
      }
    }
  ],
  "totals": {
    "energy_kwh_month": 14.1234,
    "carbon_gco2e_month": 1342.12,
    "embodied_gco2e_month": 967.44,
    "cost_usd_month": 30.37
  },
  "skipped": []
}
```

If an `API_KEY` is configured, include it in every request:

```bash
curl -H "X-API-Key: your-secret-key" ...
```

#### Estimate carbon from live AWS infrastructure

```bash
curl http://localhost:8000/api/estimate/live?region=eu-west-1
```

Requires AWS credentials to be available to the backend process.

#### JavaScript / TypeScript example

```js
const response = await fetch('http://localhost:8000/api/estimate/plan', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(terraformPlanJson),
});
const { resources, totals } = await response.json();
console.log(`Total carbon: ${totals.carbon_gco2e_month} gCO₂e/month`);
console.log(`Total cost:   $${totals.cost_usd_month}/month`);
```

#### Python (requests) example

```python
import requests

plan = { ... }  # Terraform plan JSON
response = requests.post('http://localhost:8000/api/estimate/plan', json=plan)
data = response.json()
print(f"Total carbon: {data['totals']['carbon_gco2e_month']} gCO₂e/month")
print(f"Total cost:   ${data['totals']['cost_usd_month']}/month")
```

---

### Option 2 — Python library (direct import)

Copy `calculator.py`, `cost_calculator.py`, `embodied_data.py`, and the `data/` directory into your project, then import the estimation functions directly.
This is useful when you do not want to run a separate HTTP service.

```python
import sys
sys.path.insert(0, './carbon_cost_module')  # path to your copy of this repo

from calculator import estimate_ec2, estimate_ebs_storage, estimate_rds
from cost_calculator import estimate_ec2_cost, estimate_ebs_cost, estimate_rds_cost

# Estimate an EC2 instance
carbon = estimate_ec2(
    instance_type='t3.medium',
    region='eu-west-1',
    resource_id='my-server',
)
if carbon:
    print(f"Energy:  {carbon.energy_kwh_month:.3f} kWh/month")
    print(f"Carbon:  {carbon.carbon_gco2e_month:.1f} gCO2e/month")
    if carbon.embodied_gco2e_month:
        print(f"Embodied: {carbon.embodied_gco2e_month:.1f} gCO2e/month")

# Estimate an EBS volume
ebs = estimate_ebs_storage(size_gb=100, volume_type='gp3', region='eu-west-1')
if ebs:
    print(f"EBS carbon: {ebs.carbon_gco2e_month:.1f} gCO2e/month")

# Estimate an RDS instance
rds = estimate_rds(
    instance_class='db.t3.medium',
    region='eu-west-1',
    storage_gb=100,
    storage_type='gp2',
)
if rds:
    print(f"RDS carbon: {rds.carbon_gco2e_month:.1f} gCO2e/month")
```

All three estimate functions return `None` if no wattage or grid-intensity data is available for the supplied inputs (the reason is logged at `WARNING` level). The return type is the `CarbonEstimate` dataclass defined in `calculator.py`.

For cost estimates, call the matching `estimate_*_cost()` functions from `cost_calculator.py`. These call the AWS Pricing API and require `boto3` to be installed and AWS credentials to be configured.

#### Logging

The library uses Python's standard `logging` module under the logger name of each module (`calculator`, `cost_calculator`, `terraform_estimate`). To see warning messages in your application:

```python
import logging
logging.basicConfig(level=logging.WARNING)
```

#### Refreshing embodied-carbon data

The `data/embodied.json` file caches Boavizta embodied-carbon factors. To keep it fresh in a long-running process:

```python
from embodied_data import ensure_embodied_data_current
import calculator

result = ensure_embodied_data_current(max_age_days=7, enabled=True)
calculator.reload_embodied_data()   # reload the in-memory cache after refresh
```

---

### Supported resource types

| Terraform resource type | Function | Notes |
|---|---|---|
| `aws_instance` | `estimate_ec2()` | Supports all instance types in `data/wattage.json` |
| `aws_ebs_volume` | `estimate_ebs_storage()` | SSD (gp2/gp3/io1/io2) and HDD (st1/sc1/standard) |
| `aws_db_instance` | `estimate_rds()` | Compute + storage; same wattage data as EC2 |

Resources not in this list are silently skipped by `estimate_from_plan_dict()` and logged as `skipped` in the API response.
