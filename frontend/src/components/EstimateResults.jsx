/**
 * EstimateResults.jsx
 *
 * Shared display components for rendering carbon + cost estimate results.
 * Used by both the form-based Provision view and the Live Scan view.
 */

import CarbonEquivalencies from './CarbonEquivalencies';

export function Stat({ label, value }) {
  return (
    <div>
      <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
        {label}
      </p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}

/** Render the full results panel (resource cards + totals banner + skipped list). */
export function EstimationResults({ results, comparisons, cpuUtilisation }) {
  const { resources, totals, skipped } = results;
  const totalEmbodied = totals.embodied_gco2e_month;
  const hasEmbodiedData = totalEmbodied != null || resources.some(
    (resource) => resource.carbon.embodied_gco2e_month != null,
  );
  const totalCombined = totalEmbodied != null
    ? totals.carbon_gco2e_month + totalEmbodied
    : null;

  // Group resources by type for the breakdown
  const ec2 = resources.filter((r) => r.resource_type === 'aws_instance');
  const rds = resources.filter((r) => r.resource_type === 'aws_db_instance');
  const ebs = resources.filter((r) => r.resource_type === 'aws_ebs_volume');
  const elb = resources.filter((r) => r.resource_type === 'aws_lb');

  return (
    <div className="mt-6 space-y-6">
      <h2 className="text-xl font-semibold">Audit Results</h2>

      {/* Totals */}
      {resources.length > 0 && (
        <div className="space-y-4">
          <div className="rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 p-4">
            <p className="font-semibold text-green-800 dark:text-green-200 mb-2">Energy &amp; Carbon</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <Stat label="Energy (monthly)" value={`${totals.energy_kwh_month} kWh`} />
              <Stat label="Energy (yearly)" value={`${(totals.energy_kwh_month * 12).toFixed(2)} kWh`} />
              <Stat label="Operational carbon (monthly)" value={`${totals.carbon_gco2e_month} gCO₂e`} />
              <Stat label="Operational carbon (yearly)" value={`${(totals.carbon_gco2e_month * 12).toFixed(2)} gCO₂e`} />
              <Stat
                label="Embodied carbon (monthly)"
                value={hasEmbodiedData && totalEmbodied != null ? `${totalEmbodied.toFixed(4)} gCO₂e` : 'Unavailable'}
              />
              <Stat
                label="Total carbon (monthly)"
                value={totalCombined != null ? `${totalCombined.toFixed(4)} gCO₂e` : 'Operational only'}
              />
            </div>
            <p className="mt-3 text-xs text-green-700 dark:text-green-300">
              {hasEmbodiedData
                ? 'Embodied carbon is region-independent — switching region changes operational carbon only.'
                : 'Embodied carbon data is unavailable for the current resource set, so totals show operational carbon only.'}
            </p>
            <p className="mt-2 text-xs text-green-700 dark:text-green-300">
              All carbon values are in <strong>gCO₂e</strong>. The AWS CCFT Dashboard reports in{' '}
              <strong>mtCO₂e</strong> (metric tons); 1 mtCO₂e = 1,000,000 gCO₂e. Use the Dashboard
              tab to compare these estimates against CCFT actuals.
            </p>
          </div>
          <CarbonEquivalencies carbonGco2e={totalCombined ?? totals.carbon_gco2e_month} />
          <div className="rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 p-4">
            <p className="font-semibold text-green-800 dark:text-green-200 mb-2">Cost</p>
            <div className="grid grid-cols-2 gap-4">
              <Stat label="Cost (monthly)" value={`$${totals.cost_usd_month}`} />
              <Stat label="Cost (yearly)" value={`$${(totals.cost_usd_month * 12).toFixed(2)}`} />
            </div>
          </div>
        </div>
      )}

      {/* Per-resource breakdown */}
      {ec2.length > 0 && (
        <ResourceTable
          title="EC2 Instances"
          resources={ec2}
          note={`Direct EC2 instances only. EKS managed nodes appear here as regular EC2 instances — they are included in AWS CCFT under 'AmazonEC2'. Fargate tasks are not visible. Carbon estimated at ${cpuUtilisation != null ? Math.round(cpuUtilisation * 100) : 50}% CPU utilisation.`}
        />
      )}
      {rds.length > 0 && (
        <ResourceTable
          title="RDS Instances"
          resources={rds}
          note="Available RDS instances in this region. Aurora Serverless and instances in other accounts are not included."
        />
      )}
      {ebs.length > 0 && (
        <ResourceTable
          title="EBS Volumes"
          resources={ebs}
          note="In-use EBS volumes only. Unattached volumes are not included. AWS CCFT bundles EBS emissions within the 'AmazonEC2' service category."
        />
      )}

      {skipped.length > 0 && (
        <div className="rounded border border-yellow-300 bg-yellow-50 dark:bg-yellow-950 dark:border-yellow-800 p-3 text-sm text-yellow-700 dark:text-yellow-400">
          <span className="font-semibold">Skipped</span> — no wattage data available for: {skipped.join(', ')}
        </div>
      )}

      {comparisons && <RegionComparisonPanel comparisons={comparisons} />}
    </div>
  );
}

/** Per-resource breakdown table. */
function ResourceTable({ title, resources, note }) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <p className="font-semibold text-sm">{title} <span className="font-normal text-gray-500 dark:text-gray-400">({resources.length})</span></p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              <th className="text-left px-4 py-2">Resource</th>
              <th className="text-right px-4 py-2">Operational/mo</th>
              <th className="text-right px-4 py-2">Embodied/mo</th>
              <th className="text-right px-4 py-2">Energy/mo</th>
              <th className="text-right px-4 py-2">Cost/mo</th>
              <th className="text-right px-4 py-2">Cost/yr</th>
            </tr>
          </thead>
          <tbody>
            {resources.map((r) => (
              <tr key={r.address} className="border-b border-gray-100 dark:border-gray-800 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-2">
                  <p className="font-medium text-gray-900 dark:text-gray-100 font-mono text-xs">{r.address}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{r.region}</p>
                </td>
                <td className="px-4 py-2 text-right">{r.carbon.carbon_gco2e_month} gCO₂e</td>
                <td className="px-4 py-2 text-right">
                  {r.carbon.embodied_gco2e_month != null ? `${r.carbon.embodied_gco2e_month} gCO₂e` : '—'}
                </td>
                <td className="px-4 py-2 text-right">{r.carbon.energy_kwh_month} kWh</td>
                <td className="px-4 py-2 text-right">{r.cost ? `$${r.cost.cost_usd_month}` : '—'}</td>
                <td className="px-4 py-2 text-right">{r.cost ? `$${(r.cost.cost_usd_month * 12).toFixed(2)}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-2 bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700">
        <p className="text-xs text-gray-400 dark:text-gray-500 italic">{note}</p>
      </div>
    </div>
  );
}

/** Region comparison panel — shows the same resource estimated across three green regions. */
export function RegionComparisonPanel({ comparisons }) {
  if (!comparisons || comparisons.length === 0) return null;

  const valid = comparisons.filter(
    (c) => c.result && c.result.resources.length > 0,
  );
  if (valid.length === 0) return null;

  const greenest = valid.reduce((min, c) => {
    const carbon = c.result.resources[0]?.carbon.carbon_gco2e_month ?? Infinity;
    const minCarbon =
      min.result.resources[0]?.carbon.carbon_gco2e_month ?? Infinity;
    return carbon < minCarbon ? c : min;
  }, valid[0]);

  return (
    <div className="mt-6 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950 p-4">
      <h3 className="text-lg font-semibold text-blue-800 dark:text-blue-200 mb-1">
        Region Comparison
      </h3>
      <p className="text-sm text-blue-700 dark:text-blue-300 mb-4">
        Same resource estimated in three of the greenest AWS regions. Operational
        carbon changes by region; embodied carbon stays the same.
      </p>
      <div className="space-y-2">
        {valid.map((c) => {
          const resource = c.result.resources[0];
          const isGreenest = c.region === greenest.region;
          return (
            <div
              key={c.region}
              className={`rounded p-3 flex items-center justify-between ${
                isGreenest
                  ? 'bg-green-100 dark:bg-green-900 border border-green-300 dark:border-green-700'
                  : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700'
              }`}
            >
              <div>
                <span className="font-medium text-sm">{c.label}</span>
                {isGreenest && (
                  <span className="ml-2 text-xs bg-green-500 text-white rounded px-1.5 py-0.5">
                    Greenest
                  </span>
                )}
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold">
                  Operational: {resource.carbon.carbon_gco2e_month} gCO₂e/mo
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Embodied: {resource.carbon.embodied_gco2e_month != null ? `${resource.carbon.embodied_gco2e_month} gCO₂e/mo` : '—'}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {resource.carbon.energy_kwh_month} kWh/mo
                  {resource.cost ? ` · $${resource.cost.cost_usd_month}/mo` : ''}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
