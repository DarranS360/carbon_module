import CcftComparisonChart from '../components/CcftComparisonChart';
import BillingChart from '../components/BillingChart';

export default function Dashboard({ useStubData = false }) {
  return (
    <main className="flex flex-col px-4 py-8 gap-12 max-w-5xl mx-auto w-full">
      <div className="text-center">
        <h1 className="text-3xl font-semibold">Dashboard</h1>
        <p className="text-gray-500 mt-2">
          {useStubData
            ? 'Stubbed carbon and cost data to demonstrate dashboard functionality.'
            : 'Real carbon and cost data for your AWS account from CCFT and Cost Explorer.'}
        </p>
        {!useStubData && (
          <details className="mt-2 text-left max-w-xl mx-auto">
            <summary className="cursor-pointer text-sm text-green-700 dark:text-green-400">
              Data source details
            </summary>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              Carbon is pulled from AWS Customer Carbon Footprint Tool (CCFT) and cost data is pulled
              from AWS Cost Explorer to compare environmental and financial trends month by month.
            </p>
          </details>
        )}
      </div>

      <CcftComparisonChart useStubData={useStubData} />
      <BillingChart useStubData={useStubData} />
    </main>
  );
}
