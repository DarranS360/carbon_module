from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WATTAGE_PATH = DATA_DIR / "wattage.json"
EMBODIED_PATH = DATA_DIR / "embodied.json"
BOAVIZTA_URL = "https://api.boavizta.org/v1/cloud/instance"
EMBODIED_SOURCE = (
    "Boavizta API /v1/cloud/instance impacts.gwp.embedded.value "
    "(kgCO2e/hour, amortised)"
)
EMBODIED_NOTE = (
    "Embodied carbon is region-independent. Values are per instance type "
    "and converted to gCO2e/month at runtime."
)


def load_instance_types() -> list[str]:
    with WATTAGE_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return sorted(k for k in raw.keys() if not k.startswith("_"))


def load_embodied_raw() -> dict:
    if not EMBODIED_PATH.exists():
        return {}

    with EMBODIED_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_embodied_factors(raw: dict) -> dict[str, float]:
    factors = dict(raw)
    factors.pop("_source", None)
    factors.pop("_note", None)
    factors.pop("_fetched_at", None)
    return factors


def fetch_embodied_kgco2e_per_hour(instance_type: str) -> float:
    query = urlencode(
        {
            "provider": "aws",
            "instance_type": instance_type,
            "verbose": "false",
            "duration": "1",
        }
    )
    req = Request(f"{BOAVIZTA_URL}?{query}", headers={"Accept": "application/json"})
    with urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    value = payload["impacts"]["gwp"]["embedded"]["value"]
    return float(value)


def refresh_embodied_file(logger: logging.Logger | None = None) -> dict:
    instance_types = load_instance_types()
    embodied: dict[str, float] = {}
    skipped: dict[str, str] = {}

    for instance_type in instance_types:
        try:
            embodied[instance_type] = fetch_embodied_kgco2e_per_hour(instance_type)
        except (KeyError, TypeError, ValueError, HTTPError, URLError, TimeoutError) as err:
            skipped[instance_type] = str(err)

    output = {
        "_source": EMBODIED_SOURCE,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_note": EMBODIED_NOTE,
        **embodied,
    }
    EMBODIED_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if logger is not None:
        logger.info(
            "Refreshed embodied carbon lookup with %s factors (%s skipped)",
            len(embodied),
            len(skipped),
        )

    return {
        "refreshed": True,
        "factor_count": len(embodied),
        "skipped_count": len(skipped),
    }


def ensure_embodied_data_current(
    *,
    max_age_days: int,
    enabled: bool,
    logger: logging.Logger | None = None,
) -> dict:
    raw = load_embodied_raw()
    factors = extract_embodied_factors(raw)

    if not enabled:
        return {
            "refreshed": False,
            "reason": "disabled",
            "factor_count": len(factors),
        }

    fetched_at_raw = raw.get("_fetched_at")
    fetched_at = None
    if isinstance(fetched_at_raw, str):
        try:
            fetched_at = datetime.fromisoformat(fetched_at_raw)
        except ValueError:
            fetched_at = None

    now = datetime.now(timezone.utc)
    is_stale = fetched_at is None or fetched_at < now - timedelta(days=max_age_days)
    needs_refresh = len(factors) == 0 or is_stale

    if not needs_refresh:
        return {
            "refreshed": False,
            "reason": "fresh",
            "factor_count": len(factors),
        }

    try:
        return refresh_embodied_file(logger=logger)
    except Exception:
        if logger is not None:
            logger.exception("Failed to refresh embodied carbon lookup")
        return {
            "refreshed": False,
            "reason": "refresh_failed",
            "factor_count": len(factors),
        }