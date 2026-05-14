import { useState } from 'react';
import ResourceForm from '../components/ResourceForm';

const RESOURCE_TYPES = [
  { value: 'aws_instance', label: 'EC2 Instance' },
  { value: 'aws_db_instance', label: 'RDS Instance' },
  { value: 'aws_ebs_volume', label: 'EBS Volume' },
];

export default function Provision() {
  const [resourceType, setResourceType] = useState('');

  return (
    <main className="flex flex-col items-center px-4 py-8 gap-6">
      <div className="text-center">
        <h1 className="text-3xl font-semibold">Provision</h1>
        <p className="text-gray-500 mt-2">
          Fill in the resource details below to estimate its carbon footprint
          and AWS cost before provisioning.
        </p>
      </div>

      <div className="w-full max-w-xl">
        <label
          htmlFor="resource-type-select"
          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          Resource Type
        </label>
        <select
          id="resource-type-select"
          value={resourceType}
          onChange={(e) => setResourceType(e.target.value)}
          className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-green-500"
        >
          <option value="">Select a resource type…</option>
          {RESOURCE_TYPES.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {resourceType && <ResourceForm key={resourceType} resourceType={resourceType} />}
    </main>
  );
}
