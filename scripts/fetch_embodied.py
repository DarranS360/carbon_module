"""
Fetch embodied carbon factors from Boavizta for AWS instance types.

Reads instance types from data/wattage.json and writes data/embodied.json.
Values are stored as kgCO2e/hour (Boavizta's amortised per-instance factor).
"""

from __future__ import annotations

import sys
from embodied_data import EMBODIED_PATH, load_instance_types, refresh_embodied_file


def main() -> int:
    instance_types = load_instance_types()

    print(f"Fetching embodied factors for {len(instance_types)} instance types...")
    result = refresh_embodied_file()
    print(
        f"Wrote {result['factor_count']} factors to {EMBODIED_PATH} "
        f"({result['skipped_count']} skipped)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
