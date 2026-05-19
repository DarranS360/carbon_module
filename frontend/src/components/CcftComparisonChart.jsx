/**
 * CcftComparisonChart.jsx
 *
 * Two separate charts showing AWS CCFT actuals in gCO₂e:
 *  - Location-Based Method (LBM) — grid carbon intensity
 *  - Market-Based Method (MBM)   — after renewable energy certificates
 *
 * 1 mtCO₂e = 1,000,000 gCO₂e
 */

import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import client from '../api/client';
import { STUB_CCFT_SUMMARY } from '../data/stubData';
import CarbonEquivalencies from './CarbonEquivalencies';

const MT_TO_G = 1_000_000;
const formatNumber = (value) => Number(value ?? 0).toFixed(2);

function formatMonth(dateStr) {
  if (!dateStr) return '';
  const [year, month] = dateStr.split('-');
  return new Date(Number(year), Number(month) - 1, 1)
    .toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
}

function toG(mt) {
  return mt != null ? parseFloat((mt * MT_TO_G).toFixed(2)) : null;
}

function buildChartData(ccftData, method) {
  if (!ccftData?.entries?.length) return [];
  return ccftData.entries.map((entry) => ({
    month: formatMonth(entry.start),
    ec2:   toG(entry.services?.AmazonEC2?.[`${method}_mtco2e`]),
  }));
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm shadow">
      <p className="font-semibold mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value != null ? `${formatNumber(p.value)} gCO₂e` : 'N/A'}
        </p>
      ))}
    </div>
  );
}

function CcftChart({ data, ec2Color }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 10, right: 20, left: 20, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.15} />
        <XAxis dataKey="month" tick={{ fontSize: 12 }} angle={-40} textAnchor="end" interval={0} />
        <YAxis
          tick={{ fontSize: 12 }}
          label={{ value: 'gCO₂e', angle: -90, position: 'insideLeft', offset: 10, style: { fontSize: 12 } }}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend verticalAlign="top" height={36} />
        <Bar dataKey="ec2" name="EC2 (incl. EKS & EBS)" fill={ec2Color} radius={[3,3,0,0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function CcftComparisonChart({ useStubData = false }) {
  const [ccftData, setCcftData] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const activeData = useStubData ? STUB_CCFT_SUMMARY : ccftData;
  const activeError = useStubData ? null : error;
  const activeLoading = useStubData ? false : loading;

  const refreshCcft = async () => {
    if (useStubData) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await client.get('/api/ccft/summary');
      setCcftData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message ?? 'Failed to load CCFT data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (useStubData) return;

    let isCurrent = true;

    (async () => {
      try {
        const res = await client.get('/api/ccft/summary');
        if (!isCurrent) return;
        setCcftData(res.data);
        setError(null);
      } catch (err) {
        if (!isCurrent) return;
        setError(err.response?.data?.detail ?? err.message ?? 'Failed to load CCFT data.');
      } finally {
        if (isCurrent) setLoading(false);
      }
    })();

    return () => {
      isCurrent = false;
    };
  }, [useStubData]);

  const lbmData = buildChartData(activeData, 'lbm');
  const mbmData = buildChartData(activeData, 'mbm');
  const latestLbmGco2e = activeData?.entries?.at(-1)?.ec2_lbm_mtco2e != null
    ? activeData.entries.at(-1).ec2_lbm_mtco2e * MT_TO_G
    : null;

  return (
    <div className="w-full space-y-8">

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold">AWS Carbon Footprint (CCFT)</h2>
          <p className="text-gray-500 dark:text-gray-400 mt-1 text-sm">
            Monthly actuals from the AWS Customer Carbon Footprint Tool. All values in gCO₂e.
          </p>
        </div>
        <button
          onClick={refreshCcft}
          disabled={activeLoading}
          className="rounded border border-blue-400 text-blue-600 dark:text-blue-400 px-4 py-2 font-medium hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-60 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
        >
          {activeLoading ? 'Loading…' : '↻ Refresh'}
        </button>
      </div>

      {activeError && (
        <div className="rounded border border-red-300 bg-red-50 dark:bg-red-950 dark:border-red-800 p-3 text-red-700 dark:text-red-300 text-sm">
          <strong>CCFT error:</strong> {activeError}
        </div>
      )}

      {activeLoading && !activeData && (
        <div className="flex items-center justify-center h-64 text-gray-400">
          <span className="animate-spin h-6 w-6 border-2 border-gray-400 border-t-transparent rounded-full mr-3" />
          Loading CCFT data…
        </div>
      )}

      {!activeLoading && !activeError && activeData?.entries?.length === 0 && (
        <div className="rounded border border-yellow-300 bg-yellow-50 dark:bg-yellow-950 dark:border-yellow-800 p-4 text-yellow-700 dark:text-yellow-300 text-sm">
          No CCFT data returned. Data typically lags by ~3 months.
        </div>
      )}

      {lbmData.length > 0 && (
        <div className="space-y-6">

          {/* LBM Chart */}
          <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-white dark:bg-gray-900 p-4">
            <div className="mb-3">
              <h3 className="text-lg font-semibold text-blue-800 dark:text-blue-200">
                Location-Based Method (LBM)
              </h3>
              <details className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                <summary className="cursor-pointer text-blue-700 dark:text-blue-300">Method details</summary>
                <p className="mt-2">
                  Carbon emissions calculated using the actual carbon intensity of the electricity grid
                  in each AWS region. This is the most accurate reflection of the real-world carbon
                  impact of your infrastructure and is directly comparable to the estimates this tool
                  produces. <strong>Use this to understand your true carbon footprint and to benchmark
                  against regional grid improvements over time.</strong>
                </p>
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  Note: CCFT reports in <strong>mtCO₂e</strong> (metric tons); values here have been
                  converted to <strong>gCO₂e</strong> for comparison with the Infrastructure Audit.
                  1 mtCO₂e = 1,000,000 gCO₂e. Only the <strong>AmazonEC2</strong> service category is
                  shown — this covers EC2 instances, EKS worker nodes, and attached EBS volumes,
                  matching the scope of the Infrastructure Audit. Elastic Load Balancers, RDS, and
                  other services are intentionally excluded from this chart.
                </p>
              </details>
            </div>
            <CcftChart data={lbmData} ec2Color="#3b82f6" />
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
              AmazonEC2 covers EC2 instances, EKS node groups, and attached EBS volumes. Scope matches the Infrastructure Audit.
            </p>
          </div>

          {latestLbmGco2e != null && (
            <CarbonEquivalencies carbonGco2e={latestLbmGco2e} />
          )}

          {/* MBM Chart */}
          <div className="rounded-lg border border-purple-200 dark:border-purple-800 bg-white dark:bg-gray-900 p-4">
            <div className="mb-3">
              <h3 className="text-lg font-semibold text-purple-800 dark:text-purple-200">
                Market-Based Method (MBM)
              </h3>
              <details className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                <summary className="cursor-pointer text-purple-700 dark:text-purple-300">Method details</summary>
                <p className="mt-2">
                  Carbon emissions after accounting for renewable energy certificates (RECs) and
                  Power Purchase Agreements (PPAs) that AWS has purchased on your behalf. MBM figures
                  are typically lower than LBM because AWS invests heavily in renewable energy.
                  <strong> Use this for sustainability reporting and ESG disclosures where you want
                  to reflect the benefit of AWS&apos;s renewable energy commitments.</strong> The gap
                  between LBM and MBM represents the carbon offset from those purchases.
                </p>
              </details>
            </div>
            <CcftChart data={mbmData} ec2Color="#8b5cf6" />
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
              MBM will always be ≤ LBM. A smaller gap indicates less renewable energy coverage in that region.
            </p>
          </div>

        </div>
      )}
    </div>
  );
}
