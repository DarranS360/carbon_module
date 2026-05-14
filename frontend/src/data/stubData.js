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

export function getStubLiveScanResults(region) {
  return {
    ...STUB_LIVE_SCAN_RESULTS,
    resources: STUB_LIVE_SCAN_RESULTS.resources.map((resource) => ({
      ...resource,
      region,
    })),
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
