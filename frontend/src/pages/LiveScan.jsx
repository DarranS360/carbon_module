import { useState } from 'react';
import client from '../api/client';
import { EstimationResults } from '../components/EstimateResults';
import { getStubLiveScanResults } from '../data/stubData';

const REGIONS = [
  { value: 'eu-west-1', label: 'EU (Ireland) — eu-west-1' },
  { value: 'eu-west-2', label: 'EU (London) — eu-west-2' },
  { value: 'us-east-1', label: 'US East (N. Virginia) — us-east-1' },
];

const CPU_PRESETS = [
  { label: '50% (CCF default)', value: 0.50 },
];

export default function LiveScan({ useStubData = false }) {
  const [region, setRegion] = useState('eu-west-1');
  const [cpuUtilisation, setCpuUtilisation] = useState(0.50);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleScan = async () => {
    setLoading(true);
    setError(null);
    setResults(null);

    if (useStubData) {
      setResults(getStubLiveScanResults(region, cpuUtilisation));
      setLoading(false);
      return;
    }

    try {
      const response = await client.get('/api/estimate/live', {
        params: { region, cpu_utilisation: cpuUtilisation },
      });
      setResults(response.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ??
          err.message ??
          'Failed to run live scan. Ensure AWS credentials are configured and try again.',
      );
    } finally {
      setLoading(false);
    }
  };

  const pct = Math.round(cpuUtilisation * 100);

  return (
    <main className="flex flex-col items-center px-4 py-8 gap-6">
      <div className="text-center">
        <h1 className="text-3xl font-semibold">Infrastructure Audit</h1>
        <p className="text-gray-500 mt-2">
          {useStubData
            ? 'Using stubbed infrastructure data to demonstrate the audit workflow without AWS credentials.'
            : 'Inspect running AWS infrastructure in a region to review estimated carbon footprint and on-demand cost.'}
        </p>
        {!useStubData && (
          <details className="mt-2 text-left max-w-xl mx-auto">
            <summary className="cursor-pointer text-sm text-green-700 dark:text-green-400">
              More audit guidance
            </summary>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              Use this to identify over-provisioned or unexpectedly running resources before they appear
              on your bill or carbon report.
            </p>
          </details>
        )}
      </div>

      <div className="w-full max-w-xl flex flex-col gap-4">
        <div>
          <label
            htmlFor="region-select"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            AWS Region
          </label>
          <select
            id="region-select"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-green-500"
          >
            {REGIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {/* EC2 CPU utilisation */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label
              htmlFor="cpu-slider"
              className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-1"
            >
              EC2 CPU Utilisation assumption
              <span
                role="img"
                aria-label="Used only for EC2 carbon estimation. The CCF methodology default is 50%. EBS volumes are unaffected."
                title="Used only for EC2 carbon estimation. The CCF methodology default is 50%. EBS volumes are unaffected."
                className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-gray-400 text-[10px] text-gray-500 dark:border-gray-500 dark:text-gray-400"
              >
                i
              </span>
            </label>
            <span className="text-sm font-semibold text-green-700 dark:text-green-400 tabular-nums">
              {pct}%
            </span>
          </div>
          <input
            id="cpu-slider"
            type="range"
            min={1}
            max={100}
            step={1}
            value={pct}
            onChange={(e) => setCpuUtilisation(Number(e.target.value) / 100)}
            className="w-full accent-green-600"
          />
          <div className="flex gap-2 mt-2">
            {CPU_PRESETS.map(({ label, value }) => (
              <button
                key={value}
                type="button"
                onClick={() => setCpuUtilisation(value)}
                className={`text-xs px-2 py-1 rounded border transition-colors ${
                  cpuUtilisation === value
                    ? 'bg-green-600 text-white border-green-600'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-green-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={handleScan}
          disabled={loading}
          className="w-full rounded bg-green-600 px-4 py-2 text-white font-medium hover:bg-green-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full inline-block" />
              Scanning…
            </span>
          ) : (
            'Scan Infrastructure'
          )}
        </button>

        {error && (
          <div className="rounded border border-red-300 bg-red-50 dark:bg-red-950 dark:border-red-800 p-4 text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {results && results.resources.length === 0 && (
          <div className="rounded border border-yellow-300 bg-yellow-50 dark:bg-yellow-950 dark:border-yellow-800 p-4 text-yellow-700 dark:text-yellow-300">
            No running resources found in <strong>{region}</strong>.
          </div>
        )}

        {results && results.resources.length > 0 && (
          <EstimationResults results={results} cpuUtilisation={cpuUtilisation} />
        )}
      </div>
    </main>
  );
}
