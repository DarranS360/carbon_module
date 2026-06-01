# Test Plan — Carbon Cost Module

## Overview

This document describes the testing strategy for the Carbon Cost Module:
its rationale, what was deliberately excluded, and a mapping of each test
to the defect class it protects against.

---

## 1. Testing Approach and Rationale

Three complementary tiers of testing were chosen:

| Tier | Method | Tooling |
|------|--------|---------|
| Unit | Pure function tests with hand-calculated assertions | `pytest` |
| Integration | Endpoint tests with mocked AWS using `TestClient` | `pytest` + `httpx` + `unittest.mock` |
| Operational validation | Compare tool estimates against AWS CCFT export | Manual / documented in M4 |

### Why unit tests first?

`calculator.py` functions are **deterministic**: given a fixed instance type,
region, and utilisation, the output is a closed-form arithmetic expression.
That makes it straightforward to derive the expected answer by hand and assert
equality to machine precision.  Any future regression (wrong coefficient,
mis-applied PUE, wrong grid-intensity lookup) will cause an immediate,
pinpoint failure.

### Why mock boto3 for integration tests?

The API endpoints call live AWS services.  Requiring real credentials in CI
would make the tests flaky and environment-dependent.  Mocking boto3 with
`unittest.mock.patch` lets us test **our code** (routing, request parsing,
response serialisation, error handling) without testing AWS itself.  This is
standard practice for cloud-connected applications.

### Why include CCFT validation as the third tier?

Unit and integration tests prove internal correctness.  They cannot answer
whether the *methodology* produces directionally correct numbers in practice.
Comparing the tool's estimate against the AWS Customer Carbon Footprint Tool
(CCFT) for the same account and period answers that question.  The CCFT
provides an independently-produced ground truth for operational carbon, making
it the most academically valuable form of evaluation for an estimation tool.

---

## 2. Deliberate Exclusions

| Exclusion | Reason |
|-----------|--------|
| **Frontend / UI testing** | The React dashboard is a visualisation layer only; no business logic lives there. UI testing (e.g. Playwright, Cypress) would add significant tooling overhead for low information gain. |
| **Exhaustive API permutation testing** | Testing every combination of instance type × region × storage type would produce thousands of tests without finding additional bug classes. The chosen tests cover the happy path and the main failure modes. |
| **Cost calculator unit tests** (`cost_calculator.py`) | This module calls the AWS Pricing API at runtime; meaningful unit tests would just re-test mocked HTTP responses, not the pricing logic itself. Integration-level coverage via the plan endpoint provides sufficient protection. |
| **End-to-end AWS live tests** | Would require valid credentials, a provisioned account, and would be slow and non-deterministic. Validated manually using a real Fujitsu AWS workload (see M4). |

---

## 3. Test Map

### Unit tests — `tests/test_calculator.py`

| Test | Function under test | What it validates | Why it matters |
|------|---------------------|-------------------|----------------|
| `test_known_instance_and_region_returns_estimate` | `estimate_ec2` | Returns a result (not `None`) for a valid input | Guards against silent data-loading failures |
| `test_energy_value_matches_formula` | `estimate_ec2` | Energy equals `(min + util × (max − min)) × hours / 1000 × PUE` | Catches coefficient or PUE substitution bugs |
| `test_carbon_value_matches_formula` | `estimate_ec2` | Carbon equals `energy × grid × 1000` | Catches wrong grid intensity or unit conversion |
| `test_different_region_uses_different_grid_intensity` | `estimate_ec2` | EU and US produce different carbon figures | Catches a "hard-coded region" bug |
| `test_unknown_instance_type_returns_none` | `estimate_ec2` | Returns `None` gracefully | Prevents a `KeyError` crashing the API |
| `test_unknown_region_returns_none` | `estimate_ec2` | Returns `None` gracefully | Same protection for the region lookup |
| `test_result_metadata_is_correct` | `estimate_ec2` | `resource_type`, `region`, `instance_type` fields match inputs | Guards against swapped or missing metadata |
| `test_ssd_volume_uses_ssd_coefficient` | `estimate_ebs_storage` | `gp2` uses 1.2 wh/TB-hr | Catches wrong coefficient for SSD types |
| `test_hdd_volume_uses_hdd_coefficient` | `estimate_ebs_storage` | `st1` uses 0.65 wh/TB-hr | Catches wrong coefficient for HDD types |
| `test_ssd_carbon_higher_than_hdd_for_same_size` | `estimate_ebs_storage` | SSD emits more than HDD at identical size | Directional sanity check |
| `test_gp3_treated_as_ssd` | `estimate_ebs_storage` | `gp3` maps to SSD path | Catches omission of newer volume types |
| `test_unknown_region_returns_none` | `estimate_ebs_storage` | Returns `None` for unknown region | Consistent edge-case handling |
| `test_result_resource_type` | `estimate_ebs_storage` | `resource_type == "aws_ebs_volume"` | Prevents dashboard misclassification |
| `test_known_class_and_region_returns_estimate` | `estimate_rds` | Returns a result for a valid RDS class | Guards against DB wattage-table omissions |
| `test_compute_and_storage_components_add_to_total` | `estimate_rds` | `total = compute + storage` (within rounding) | Catches off-by-one or double-count bugs |
| `test_carbon_equals_total_energy_times_grid` | `estimate_rds` | Carbon is correctly derived from total energy | Verifies the RDS carbon formula end-to-end |
| `test_hdd_storage_type_uses_hdd_coefficient` | `estimate_rds` | `magnetic` storage uses HDD coefficient | Ensures RDS respects HDD storage types |
| `test_unknown_region_returns_none` | `estimate_rds` | Returns `None` for unknown region | Consistent with EC2 / EBS behaviour |
| `test_unknown_instance_class_still_returns_estimate` | `estimate_rds` | Unknown class → compute 0, storage still estimated | Partial data should not silently lose storage carbon |
| `test_result_resource_type` | `estimate_rds` | `resource_type == "aws_db_instance"` | Prevents dashboard misclassification |
| `test_known_instance_returns_float` | `estimate_embodied` | Returns a positive float for a known Boavizta instance | Guards against a broken JSON load |
| `test_value_scales_with_hours` | `estimate_embodied` | Result doubles when hours doubles | Verifies linear scaling |
| `test_unknown_instance_returns_none` | `estimate_embodied` | Returns `None` for an absent entry | Prevents `AttributeError` in callers |

### Integration tests — `tests/test_api.py`

| Test | Endpoint | What it validates | Why it matters |
|------|----------|-------------------|----------------|
| `test_valid_plan_returns_200` | `POST /api/estimate/plan` | HTTP 200 for a well-formed plan | Catches routing or serialisation regressions |
| `test_response_contains_required_keys` | `POST /api/estimate/plan` | `resources`, `totals`, `skipped` present | Dashboard depends on these keys |
| `test_resources_list_is_non_empty` | `POST /api/estimate/plan` | Three resources → three estimates | Catches silent skipping |
| `test_totals_contain_carbon_and_energy` | `POST /api/estimate/plan` | Totals > 0 for a real workload | Catches zero-value aggregation bugs |
| `test_each_resource_has_carbon_block` | `POST /api/estimate/plan` | Every resource has a `carbon` sub-dict | Ensures consistent response schema |
| `test_unsupported_resource_type_goes_to_skipped` | `POST /api/estimate/plan` | Unknown resource type in `skipped` | Validates graceful degradation |
| `test_empty_plan_returns_empty_results` | `POST /api/estimate/plan` | No resources → empty lists | Edge case: empty plan should not error |
| `test_live_returns_200` | `GET /api/estimate/live` | HTTP 200 with mocked credentials | Verifies happy-path routing |
| `test_live_response_shape` | `GET /api/estimate/live` | Same shape as plan endpoint | Ensures API contract consistency |
| `test_live_includes_ec2_resource` | `GET /api/estimate/live` | EC2 instance appears in resources | Verifies EC2 scraping and estimation path |
| `test_live_invalid_credentials_returns_503` | `GET /api/estimate/live` | 503 when STS call fails | Correct error surfacing to the dashboard |
| `test_ccft_returns_200` | `GET /api/ccft/summary` | HTTP 200 with mocked CCFT response | Basic routing check |
| `test_ccft_response_shape` | `GET /api/ccft/summary` | `period`, `total_entries`, `entries` present | Dashboard depends on these keys |
| `test_ccft_entries_contain_emission_totals` | `GET /api/ccft/summary` | LBM and MBM totals are correct | Verifies CCFT aggregation logic |
| `test_ccft_no_credentials_returns_503` | `GET /api/ccft/summary` | 503 on `NoCredentialsError` | Correct error surfacing |
| `test_billing_returns_200` | `GET /api/billing/summary` | HTTP 200 with mocked CE response | Basic routing check |
| `test_billing_response_shape` | `GET /api/billing/summary` | `period`, `total_entries`, `entries` present | Dashboard depends on these keys |
| `test_billing_tax_excluded_from_total` | `GET /api/billing/summary` | Tax line excluded from monthly total | Correct billing calculation |
| `test_billing_known_service_labelled_correctly` | `GET /api/billing/summary` | EC2 appears under its human-readable label | Dashboard label correctness |
| `test_billing_no_credentials_returns_503` | `GET /api/billing/summary` | 503 on `NoCredentialsError` | Consistent error handling |

---

## 4. CCFT Validation as Formal Evaluation (M4)

> **M4** refers to Milestone 4 in the project plan — the operational validation
> deliverable that compares tool estimates against real AWS billing data.

In addition to automated tests, the tool's estimates are validated against a
real-world ground truth using the AWS Customer Carbon Footprint Tool:

**Input:** a Fujitsu AWS workload consisting of EKS worker nodes (EC2
instances), associated EBS storage, and RDS instances, running in
`eu-west-1`.

**Method:** export monthly carbon data from the CCFT for the same account and
the same 12-month period.  Run the Carbon Cost Module's live-scan endpoint
against the same account.  Compare total operational carbon figures.

**Expected output:**

| Source | Scope | Typical gap |
|--------|-------|-------------|
| CCFT export | Operational carbon only; AWS-reported | — (baseline) |
| Carbon Cost Module | Operational (CCF formula) + optional embodied | +5 % to +20 % when embodied included |

**Known sources of divergence:**

1. **CPU utilisation assumption** — the tool defaults to 50 % average
   utilisation.  Actual utilisation (from CloudWatch) will differ, directly
   scaling the operational estimate.
2. **Infrastructure scope** — CCFT covers all services in the account
   (including managed services such as S3, CloudFront, and Lambda) that the
   module does not yet model.  This makes the CCFT total *higher* than the
   module estimate for multi-service accounts.
3. **Embodied carbon** — CCFT reports operational carbon only.  The module
   can optionally include Boavizta-derived embodied carbon per instance.
4. **Grid intensity vintage** — the module uses annual-average CCF grid
   intensity values; CCFT uses AWS's own marginal intensity figures.

