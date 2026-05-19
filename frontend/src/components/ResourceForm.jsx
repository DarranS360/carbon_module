import { useEffect, useId, useRef, useState } from 'react';
import Form from '@rjsf/core';
import validator from '@rjsf/validator-ajv8';
import client from '../api/client';
import ec2Schema from '../schemas/ec2.json';
import rdsSchema from '../schemas/rds.json';
import ebsSchema from '../schemas/ebs.json';
import { EstimationResults } from './EstimateResults';

/** Map from Terraform resource type to the bundled JSON schema. */
const SCHEMA_MAP = {
  aws_instance: ec2Schema,
  aws_db_instance: rdsSchema,
  aws_ebs_volume: ebsSchema,
};

/**
 * Three of the globally-greenest AWS regions used for the region comparison
 * panel.  Values are purely for labelling — the backend derives its own grid
 * intensity from the same source-of-truth data file.
 */
const COMPARISON_REGIONS = [
  { region: 'eu-north-1',    label: 'Stockholm (eu-north-1)' },
  { region: 'eu-west-3',     label: 'Paris (eu-west-3)' },
  { region: 'ap-southeast-6', label: 'New Zealand (ap-southeast-6)' },
];

/**
 * Transform RJSF form data into the `after` values shape the backend expects.
 *
 * The JSON schemas use user-friendly field names; the Terraform plan format
 * uses the actual Terraform attribute names, which differ for RDS and EBS.
 *
 * The `region` field is omitted here because it is placed in the provider
 * config block of the synthetic plan rather than in `after`.
 */
function toAfterValues(resourceType, formData) {
  // Build a copy without `region` — it goes in the provider config instead.
  const after = { ...formData };
  delete after.region;

  if (resourceType === 'aws_db_instance') {
    // storage_gb (schema) → allocated_storage (Terraform / backend)
    after.allocated_storage = after.storage_gb;
    delete after.storage_gb;
  }

  if (resourceType === 'aws_ebs_volume') {
    // size_gb (schema) → size (Terraform / backend)
    // volume_type (schema) → type (Terraform / backend)
    after.size = after.size_gb;
    after.type = after.volume_type;
    delete after.size_gb;
    delete after.volume_type;
  }

  // aws_instance: instance_type matches; other fields (name, environment) are
  // passed through and harmlessly ignored by the backend.
  return after;
}

/** Build a synthetic Terraform plan dict for a given region and after-values. */
function buildPlan(resourceType, region, afterValues) {
  return {
    configuration: {
      provider_config: {
        aws: {
          expressions: {
            region: { constant_value: region },
          },
        },
      },
    },
    resource_changes: [
      {
        type: resourceType,
        address: `${resourceType}.resource`,
        change: {
          actions: ['create'],
          after: afterValues,
        },
      },
    ],
  };
}

/**
 * ResourceForm
 *
 * Accepts a `resourceType` prop (e.g. "aws_instance"), loads the matching
 * JSON schema, renders it with RJSF, and on submit posts a synthetic Terraform
 * plan to /api/estimate/plan.
 */
export default function ResourceForm({ resourceType }) {
  const [results, setResults] = useState(null);
  const [comparisons, setComparisons] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const formId = useId();
  const resultsRef = useRef(null);

  const schema = SCHEMA_MAP[resourceType];

  useEffect(() => {
    if (results && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [results]);

  if (!schema) {
    return (
      <p className="text-red-500">Unknown resource type: {resourceType}</p>
    );
  }

  const handleSubmit = async ({ formData }) => {
    setLoading(true);
    setError(null);
    setResults(null);
    setComparisons(null);

    const region = formData.region;
    const afterValues = toAfterValues(resourceType, formData);

    const mainPlan = buildPlan(resourceType, region, afterValues);
    const comparisonPlans = COMPARISON_REGIONS.map(({ region: r }) =>
      buildPlan(resourceType, r, afterValues),
    );

    try {
      // Fetch the main estimate and all three comparison estimates in parallel.
      // Promise.allSettled ensures comparison failures don't hide a successful
      // main estimate.
      const [mainOutcome, ...compOutcomes] = await Promise.allSettled([
        client.post('/api/estimate/plan', mainPlan).then((r) => r.data),
        ...comparisonPlans.map((p) =>
          client.post('/api/estimate/plan', p).then((r) => r.data),
        ),
      ]);

      if (mainOutcome.status === 'rejected') {
        const err = mainOutcome.reason;
        throw err;
      }

      setResults(mainOutcome.value);
      setComparisons(
        COMPARISON_REGIONS.map((c, i) =>
          compOutcomes[i].status === 'fulfilled'
            ? { ...c, result: compOutcomes[i].value }
            : { ...c, result: null },
        ),
      );
    } catch (err) {
      setError(
        err.response?.data?.detail ??
          err.message ??
          'Failed to fetch carbon estimate. Please try again or contact support if the issue persists.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-xl">
      <Form
        id={formId}
        schema={schema}
        validator={validator}
        onSubmit={handleSubmit}
        uiSchema={{ 'ui:submitButtonOptions': { norender: true } }}
        className="rjsf"
      />

      <button
        type="submit"
        form={formId}
        disabled={loading}
        className="mt-4 w-full rounded bg-green-600 px-4 py-2 text-white font-medium hover:bg-green-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full inline-block" />
            Estimating…
          </span>
        ) : (
          'Get Estimate'
        )}
      </button>

      {error && (
        <div className="mt-4 rounded border border-red-300 bg-red-50 dark:bg-red-950 dark:border-red-800 p-4 text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {results && (
        <div ref={resultsRef}>
          <EstimationResults
            results={results}
            comparisons={comparisons}
            showResourceBreakdown={false}
          />
        </div>
      )}
    </div>
  );
}
