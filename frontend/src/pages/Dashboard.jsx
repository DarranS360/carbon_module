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
      </div>

      <CcftComparisonChart useStubData={useStubData} />
      <BillingChart useStubData={useStubData} />
    </main>
  );
}
