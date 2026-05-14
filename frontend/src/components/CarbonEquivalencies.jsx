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
  return `${gco2e.toFixed(1)} g CO₂e`;
}

function nearestRoute(routes, value) {
  return routes.reduce((prev, curr) =>
    Math.abs(curr.km - value) < Math.abs(prev.km - value) ? curr : prev,
  );
}

function driveText(driveKm) {
  const route = nearestRoute(DRIVE_ROUTES, driveKm);
  const ratio = driveKm / route.km;
  const kmStr = driveKm >= 1
    ? `${Math.round(driveKm).toLocaleString()} km`
    : `${driveKm.toFixed(1)} km`;

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
  const kmStr = `${Math.round(flightPkm).toLocaleString()} km`;

  if (ratio >= 0.9 && ratio <= 1.1) {
    return `${kmStr} in economy class — similar to flying ${route.label}`;
  }
  if (ratio < 1) {
    return `${kmStr} in economy class (${(ratio * 100).toFixed(0)}% of the flight from ${route.label})`;
  }
  return `${kmStr} in economy class (${ratio.toFixed(1)}× the flight from ${route.label})`;
}

function phoneText(phones) {
  const n = Math.round(phones);
  return `${n.toLocaleString()} full smartphone charge${n === 1 ? '' : 's'}`;
}

function treeText(treeMonths) {
  const treeCount = treeMonths / 12;
  if (treeCount >= 2)   return `What ${treeCount.toFixed(1)} mature trees absorb in a year`;
  if (treeMonths >= 2)  return `What a mature tree absorbs in ${treeMonths.toFixed(1)} months`;
  const days = Math.round(treeMonths * 30);
  return `What a mature tree absorbs in ${days} day${days === 1 ? '' : 's'}`;
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
    { icon: '🚗', text: driveText(driveKm)      },
    { icon: '✈️', text: flightText(flightPkm)   },
    { icon: '📱', text: phoneText(phones)        },
    { icon: '🌳', text: treeText(treeMonths)     },
  ];

  return (
    <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 p-4">
      <p className="font-semibold text-emerald-800 dark:text-emerald-200 mb-1">
        🌍 Real-world equivalencies
      </p>
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
      <p className="mt-3 text-xs text-emerald-600 dark:text-emerald-400">
        Sources:{' '}
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
    </div>
  );
}
