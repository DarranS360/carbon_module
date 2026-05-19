/**
 * BillingChart.jsx
 *
 * Monthly AWS cost breakdown from Cost Explorer, stacked by service.
 * Tax is excluded. Services below the top tracked list are grouped as "Other".
 */

import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import client from '../api/client';
import { STUB_BILLING_SUMMARY } from '../data/stubData';

const SERVICE_COLORS = {
  'EC2 Compute':  '#3b82f6',
  'EC2 Other':    '#60a5fa',
  'EKS':          '#06b6d4',
  'VPC':          '#8b5cf6',
  'Load Balancing': '#a78bfa',
  'CloudWatch':   '#f59e0b',
  'DynamoDB':     '#10b981',
  'Other':        '#d1d5db',
};

const ALL_SERVICES = Object.keys(SERVICE_COLORS);
const formatNumber = (value) => Number(value ?? 0).toFixed(2);

function buildChartData(billingData) {
  if (!billingData?.entries?.length) return [];
  return billingData.entries.map((entry) => ({
    month: formatMonth(entry.start),
    total: entry.total,
    ...Object.fromEntries(
      ALL_SERVICES.map((s) => [s, entry.services?.[s] ?? null])
    ),
  }));
}

function formatMonth(dateStr) {
  if (!dateStr) return '';
  const [year, month] = dateStr.split('-');
  return new Date(Number(year), Number(month) - 1, 1)
    .toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((sum, p) => sum + (p.value ?? 0), 0);
  return (
    <div className="rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm shadow min-w-40">
      <p className="font-semibold mb-1">{label}</p>
      {payload.filter((p) => p.value > 0).map((p) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: ${formatNumber(p.value)}
        </p>
      ))}
      <p className="border-t border-gray-200 dark:border-gray-700 mt-1 pt-1 font-semibold">
        Total: ${formatNumber(total)}
      </p>
    </div>
  );
}

export default function BillingChart({ useStubData = false }) {
  const [billingData, setBillingData] = useState(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const activeData = useStubData ? STUB_BILLING_SUMMARY : billingData;
  const activeError = useStubData ? null : error;
  const activeLoading = useStubData ? false : loading;

  const refreshBilling = async () => {
    if (useStubData) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await client.get('/api/billing/summary');
      setBillingData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message ?? 'Failed to load billing data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (useStubData) return;

    let isCurrent = true;

    (async () => {
      try {
        const res = await client.get('/api/billing/summary');
        if (!isCurrent) return;
        setBillingData(res.data);
        setError(null);
      } catch (err) {
        if (!isCurrent) return;
        setError(err.response?.data?.detail ?? err.message ?? 'Failed to load billing data.');
      } finally {
        if (isCurrent) setLoading(false);
      }
    })();

    return () => {
      isCurrent = false;
    };
  }, [useStubData]);

  const chartData = buildChartData(activeData);
  const latestTotal = activeData?.entries?.at(-1)?.total;

  return (
    <div className="w-full space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold">AWS Billing</h2>
          <p className="text-gray-500 dark:text-gray-400 mt-1 text-sm">
            Monthly unblended costs from AWS Cost Explorer, broken down by service. Tax excluded.
            Use this alongside the carbon data above to understand the cost-per-carbon profile
            of your infrastructure and identify which services are driving both spend and emissions.
          </p>
        </div>
        <button
          onClick={refreshBilling}
          disabled={activeLoading}
          className="rounded border border-green-400 text-green-600 dark:text-green-400 px-4 py-2 font-medium hover:bg-green-50 dark:hover:bg-green-950 disabled:opacity-60 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
        >
          {activeLoading ? 'Loading…' : '↻ Refresh'}
        </button>
      </div>

      {latestTotal && (
        <div className="rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 p-3 text-sm text-green-800 dark:text-green-200">
          Most recent month total: <strong>${formatNumber(latestTotal)}</strong>
        </div>
      )}

      {activeError && (
        <div className="rounded border border-red-300 bg-red-50 dark:bg-red-950 dark:border-red-800 p-3 text-red-700 dark:text-red-300 text-sm">
          <strong>Billing error:</strong> {activeError}
        </div>
      )}

      {activeLoading && !activeData && (
        <div className="flex items-center justify-center h-64 text-gray-400">
          <span className="animate-spin h-6 w-6 border-2 border-gray-400 border-t-transparent rounded-full mr-3" />
          Loading billing data…
        </div>
      )}

      {chartData.length > 0 && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={chartData} margin={{ top: 10, right: 20, left: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.15} />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} angle={-40} textAnchor="end" interval={0} />
              <YAxis
                tick={{ fontSize: 12 }}
                tickFormatter={(v) => `$${formatNumber(v)}`}
                label={{ value: 'USD', angle: -90, position: 'insideLeft', offset: 10, style: { fontSize: 12 } }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend verticalAlign="top" height={36} />
              {ALL_SERVICES.map((service) => (
                <Bar
                  key={service}
                  dataKey={service}
                  stackId="a"
                  fill={SERVICE_COLORS[service]}
                  radius={service === 'Other' ? [3, 3, 0, 0] : [0, 0, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
            Source: AWS Cost Explorer — unblended costs, tax excluded. EKS includes control plane and node costs.
          </p>
        </div>
      )}
    </div>
  );
}
