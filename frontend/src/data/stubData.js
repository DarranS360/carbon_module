export const STUB_LIVE_SCAN_RESULTS = {
  resources: [
    {
      address: 'aws_instance.web[0]',
      resource_type: 'aws_instance',
      region: 'eu-west-1',
      carbon: {
        energy_kwh_month: 48.36,
        carbon_gco2e_month: 4589.12,
        embodied_gco2e_month: 123.45,
      },
      cost: {
        cost_usd_month: 42.19,
      },
    },
    {
      address: 'vol-0abc123 (vol-0abc123)',
      resource_type: 'aws_ebs_volume',
      region: 'eu-west-1',
      carbon: {
        energy_kwh_month: 1.54,
        carbon_gco2e_month: 469.7,
        embodied_gco2e_month: null,
      },
      cost: {
        cost_usd_month: 8.0,
      },
    },
  ],
  skipped: [],
  totals: {
    energy_kwh_month: 49.9,
    carbon_gco2e_month: 5058.82,
    embodied_gco2e_month: 123.45,
    cost_usd_month: 50.19,
  },
};

const REGION_OPERATIONAL_MULTIPLIER = {
  'eu-west-1': 1.00,
  'eu-west-2': 1.12,
  'us-east-1': 1.28,
};

const REGION_COST_MULTIPLIER = {
  'eu-west-1': 1.00,
  'eu-west-2': 1.04,
  'us-east-1': 0.96,
};

export function getStubLiveScanResults(region, cpuUtilisation = 0.5) {
  const cpuScale = cpuUtilisation / 0.5;
  const operationalScale = REGION_OPERATIONAL_MULTIPLIER[region] ?? 1;
  const costScale = REGION_COST_MULTIPLIER[region] ?? 1;

  const resources = STUB_LIVE_SCAN_RESULTS.resources.map((resource) => {
    const isEc2 = resource.resource_type === 'aws_instance';
    const energy = isEc2 ? resource.carbon.energy_kwh_month * cpuScale : resource.carbon.energy_kwh_month;
    const operational = (isEc2 ? resource.carbon.carbon_gco2e_month * cpuScale : resource.carbon.carbon_gco2e_month) * operationalScale;

    return {
      ...resource,
      region,
      carbon: {
        ...resource.carbon,
        energy_kwh_month: Number(energy.toFixed(2)),
        carbon_gco2e_month: Number(operational.toFixed(2)),
      },
      cost: resource.cost
        ? {
            ...resource.cost,
            cost_usd_month: Number((resource.cost.cost_usd_month * costScale).toFixed(2)),
          }
        : null,
    };
  });

  const totals = resources.reduce(
    (acc, resource) => ({
      energy_kwh_month: acc.energy_kwh_month + (resource.carbon?.energy_kwh_month ?? 0),
      carbon_gco2e_month: acc.carbon_gco2e_month + (resource.carbon?.carbon_gco2e_month ?? 0),
      embodied_gco2e_month: acc.embodied_gco2e_month + (resource.carbon?.embodied_gco2e_month ?? 0),
      cost_usd_month: acc.cost_usd_month + (resource.cost?.cost_usd_month ?? 0),
    }),
    { energy_kwh_month: 0, carbon_gco2e_month: 0, embodied_gco2e_month: 0, cost_usd_month: 0 },
  );

  return {
    ...STUB_LIVE_SCAN_RESULTS,
    resources,
    totals: {
      energy_kwh_month: Number(totals.energy_kwh_month.toFixed(2)),
      carbon_gco2e_month: Number(totals.carbon_gco2e_month.toFixed(2)),
      embodied_gco2e_month: Number(totals.embodied_gco2e_month.toFixed(2)),
      cost_usd_month: Number(totals.cost_usd_month.toFixed(2)),
    },
  };
}

export const STUB_CCFT_SUMMARY = {
  period: { start: '2025-01-01', end: '2025-04-01' },
  total_entries: 3,
  entries: [
    {
      start: '2025-01-01',
      end: '2025-02-01',
      total_lbm_mtco2e: 0.95,
      total_mbm_mtco2e: 0.54,
      ec2_lbm_mtco2e: 0.71,
      ec2_mbm_mtco2e: 0.38,
      services: {
        AmazonEC2: { lbm_mtco2e: 0.71, mbm_mtco2e: 0.38 },
        Other: { lbm_mtco2e: 0.24, mbm_mtco2e: 0.16 },
      },
    },
    {
      start: '2025-02-01',
      end: '2025-03-01',
      total_lbm_mtco2e: 0.88,
      total_mbm_mtco2e: 0.5,
      ec2_lbm_mtco2e: 0.66,
      ec2_mbm_mtco2e: 0.36,
      services: {
        AmazonEC2: { lbm_mtco2e: 0.66, mbm_mtco2e: 0.36 },
        Other: { lbm_mtco2e: 0.22, mbm_mtco2e: 0.14 },
      },
    },
    {
      start: '2025-03-01',
      end: '2025-04-01',
      total_lbm_mtco2e: 0.92,
      total_mbm_mtco2e: 0.52,
      ec2_lbm_mtco2e: 0.7,
      ec2_mbm_mtco2e: 0.37,
      services: {
        AmazonEC2: { lbm_mtco2e: 0.7, mbm_mtco2e: 0.37 },
        Other: { lbm_mtco2e: 0.22, mbm_mtco2e: 0.15 },
      },
    },
  ],
};

export const STUB_BILLING_SUMMARY = {
  period: { start: '2025-01-01', end: '2025-04-01' },
  total_entries: 3,
  entries: [
    {
      start: '2025-01-01',
      end: '2025-02-01',
      total: 461.4,
      services: {
        'EC2 Compute': 231.58,
        'EC2 Other': 69.77,
        EKS: 94.51,
        VPC: 26.11,
        CloudWatch: 10.5,
        Other: 28.93,
      },
    },
    {
      start: '2025-02-01',
      end: '2025-03-01',
      total: 438.75,
      services: {
        'EC2 Compute': 220.45,
        'EC2 Other': 64.01,
        EKS: 89.26,
        VPC: 25.4,
        CloudWatch: 10.37,
        Other: 29.26,
      },
    },
    {
      start: '2025-03-01',
      end: '2025-04-01',
      total: 452.92,
      services: {
        'EC2 Compute': 224.38,
        'EC2 Other': 66.9,
        EKS: 91.7,
        VPC: 27.14,
        CloudWatch: 11.21,
        Other: 31.59,
      },
    },
  ],
};
