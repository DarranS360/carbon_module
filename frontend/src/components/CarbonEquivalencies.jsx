/**
 * CarbonEquivalencies.jsx
 *
 * Displays real-world equivalencies for a given monthly carbon footprint in gCO₂e,
 * helping users understand their cloud infrastructure impact in tangible terms.
 *
 * Conversion factors:
 *   • Car driving:    DEFRA 2023 GHG Conversion Factors — average petrol car, 0.17059 kg CO₂e/km
 *   • Economy flight: DEFRA 2023 — UK domestic economy class with radiative forcing, 0.25584 kg CO₂e/pkm
 *   • Smartphone:     Carbon Trust estimate — ~8.22 g CO₂e per full charge
 *   • Trees:          Woodland Trust UK — mature broadleaf tree absorbs ~21 kg CO₂e/year
 */

// g CO₂e per unit — sourced from DEFRA 2023 GHG Conversion Factors and other reputable references
const G_PER_CAR_KM       = 170.59;  // DEFRA 2023: average petrol car, vehicle km
const G_PER_FLIGHT_PKM   = 255.84;  // DEFRA 2023: UK domestic economy class, with radiative forcing
const G_PER_PHONE_CHARGE = 8.22;    // Carbon Trust: average smartphone full charge
const G_PER_TREE_MONTH   = 1_750;   // Woodland Trust: 21 kg CO₂e/year ÷ 12

// Named reference journeys for driving comparisons (one-way road distance in km)
const DRIVE_ROUTES = [
  { label: 'London to Brighton',    km: 84  },
  { label: 'London to Bristol',     km: 188 },
  { label: 'London to Manchester',  km: 338 },
  { label: 'London to Edinburgh',   km: 660 },
  { label: 'London to Inverness',   km: 900 },
];

// Named reference journeys for flight comparisons (great-circle passenger km)
const FLIGHT_ROUTES = [
  { label: 'London to Amsterdam', km: 357  },
  { label: 'London to Dublin',    km: 449  },
  { label: 'London to Edinburgh', km: 534  },
  { label: 'London to Malaga',    km: 1657 },
  { label: 'London to New York',  km: 5540 },
];

function formatCarbonLabel(gco2e) {
  if (gco2e >= 1_000_000) return `${(gco2e / 1_000_000).toFixed(2)} tCO₂e`;
  if (gco2e >= 1_000)     return `${(gco2e / 1_000).toFixed(2)} kg CO₂e`;
  return `${gco2e.toFixed(2)} g CO₂e`;
}

function nearestRoute(routes, value) {
  return routes.reduce((prev, curr) =>
    Math.abs(curr.km - value) < Math.abs(prev.km - value) ? curr : prev,
  );
}

function driveText(driveKm) {
  const route = nearestRoute(DRIVE_ROUTES, driveKm);
  const ratio = driveKm / route.km;
  const kmStr = `${driveKm.toFixed(2)} km`;

  if (ratio >= 0.9 && ratio <= 1.1) {
    return `${kmStr} in an average petrol car — similar to the drive from ${route.label}`;
  }
  if (ratio < 1) {
    return `${kmStr} in an average petrol car (${(ratio * 100).toFixed(0)}% of the drive from ${route.label})`;
  }
  return `${kmStr} in an average petrol car (${ratio.toFixed(1)}× the drive from ${route.label})`;
}

function flightText(flightPkm) {
  const route = nearestRoute(FLIGHT_ROUTES, flightPkm);
  const ratio = flightPkm / route.km;
  const kmStr = `${flightPkm.toFixed(2)} km`;

  if (ratio >= 0.9 && ratio <= 1.1) {
    return `${kmStr} in economy class — similar to flying ${route.label}`;
  }
  if (ratio < 1) {
    return `${kmStr} in economy class (${(ratio * 100).toFixed(0)}% of the flight from ${route.label})`;
  }
  return `${kmStr} in economy class (${ratio.toFixed(1)}× the flight from ${route.label})`;
}

function phoneText(phones) {
  const n = Number(phones.toFixed(2));
  return `${n.toLocaleString()} full smartphone charge${n === 1 ? '' : 's'}`;
}

function treeText(treeMonths) {
  const treeCount = treeMonths / 12;
  if (treeCount >= 2)   return `What ${treeCount.toFixed(2)} mature trees absorb in a year`;
  if (treeMonths >= 2)  return `What a mature tree absorbs in ${treeMonths.toFixed(2)} months`;
  const days = Number((treeMonths * 30).toFixed(2));
  return `What a mature tree absorbs in ${days} day${days === 1 ? '' : 's'}`;
}

function CarIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M5.5 12 7.8 7.8A2 2 0 0 1 9.6 6.7h4.8a2 2 0 0 1 1.8 1.1L18.5 12H20a1 1 0 0 1 1 1v3h-1a2 2 0 1 1-4 0H8a2 2 0 1 1-4 0H3v-3a1 1 0 0 1 1-1h1.5Zm2.7-1h7.6l-1.3-2.4H9.5L8.2 11Z" />
    </svg>
  );
}

function PlaneIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="m2 14 8.5-2V4.5a1.5 1.5 0 1 1 3 0V12L22 14v2l-8.5-1.2V20l2 1.2V23l-3.5-1-3.5 1v-1.8l2-1.2v-5.2L2 16v-2Z" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm5 18.2a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4ZM7 5v11h10V5H7Z" />
    </svg>
  );
}

function TreeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M11 22h2v-5h3l-3-4h2l-3-4h2l-3-4-3 4h2l-3 4h2l-3 4h3v5Z" />
    </svg>
  );
}

/**
 * CarbonEquivalencies
 *
 * @param {number} carbonGco2e  Monthly carbon footprint in grams CO₂e.
 */
export default function CarbonEquivalencies({ carbonGco2e }) {
  if (!carbonGco2e || carbonGco2e <= 0) return null;

  const driveKm    = carbonGco2e / G_PER_CAR_KM;
  const flightPkm  = carbonGco2e / G_PER_FLIGHT_PKM;
  const phones     = carbonGco2e / G_PER_PHONE_CHARGE;
  const treeMonths = carbonGco2e / G_PER_TREE_MONTH;

  const items = [
    { icon: <CarIcon />, text: driveText(driveKm) },
    { icon: <PlaneIcon />, text: flightText(flightPkm) },
    { icon: <PhoneIcon />, text: phoneText(phones) },
    { icon: <TreeIcon />, text: treeText(treeMonths) },
  ];

  return (
    <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 p-4">
      <p className="font-semibold text-emerald-800 dark:text-emerald-200 mb-1">Real-world equivalencies</p>
      <p className="text-sm text-emerald-700 dark:text-emerald-300 mb-3">
        Your estimated{' '}
        <strong>{formatCarbonLabel(carbonGco2e)}</strong> per month is roughly equivalent to:
      </p>
      <ul className="space-y-1.5 text-sm text-emerald-800 dark:text-emerald-200">
        {items.map(({ icon, text }) => (
          <li key={text} className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0">{icon}</span>
            <span>{text}</span>
          </li>
        ))}
      </ul>
      <details className="mt-3 text-xs text-emerald-600 dark:text-emerald-400">
        <summary className="cursor-pointer">Sources</summary>
        <p className="mt-2">
          <a
            href="https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2023"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-emerald-800 dark:hover:text-emerald-200"
          >
            DEFRA 2023 GHG Conversion Factors
          </a>{' '}
          (car: 0.171 kg CO₂e/km; domestic flight with RFI: 0.256 kg CO₂e/pkm) ·{' '}
          <a
            href="https://www.carbontrust.com"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-emerald-800 dark:hover:text-emerald-200"
          >
            Carbon Trust
          </a>{' '}
          (smartphone: 8.22 g CO₂e/charge) ·{' '}
          <a
            href="https://www.woodlandtrust.org.uk/trees-woods-and-wildlife/british-trees/what-trees-do-for-us/woodland-carbon/"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-emerald-800 dark:hover:text-emerald-200"
          >
            Woodland Trust
          </a>{' '}
          (tree: 21 kg CO₂e/year)
        </p>
      </details>
    </div>
  );
}
