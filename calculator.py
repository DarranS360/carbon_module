"""
calculator.py

Core carbon estimation engine.
Implements the CCF methodology formula:
  carbon = service_usage x energy_coefficient x PUE x grid_intensity

This is used for both pre-provisioning estimates (from Terraform plan)
and post-provisioning actuals (from live AWS).

Formula reference:
  https://www.cloudcarbonfootprint.org/docs/methodology/
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from embodied_data import extract_embodied_factors, load_embodied_raw

logger = logging.getLogger(__name__)

# Load lookup tables

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(DATA_DIR, "grid_intensity.json")) as f:
    GRID_INTENSITY = json.load(f)

with open(os.path.join(DATA_DIR, "wattage.json")) as f:
    INSTANCE_WATTS_RAW = json.load(f)

# Pull out metadata, keep only instance entries
PUE = INSTANCE_WATTS_RAW.pop("_pue", 1.135)
INSTANCE_WATTS_RAW.pop("_source", None)
INSTANCE_WATTS_RAW.pop("_note", None)
INSTANCE_WATTS = INSTANCE_WATTS_RAW
EMBODIED_PER_HOUR: dict[str, float] = {}


def reload_embodied_data() -> int:
    global EMBODIED_PER_HOUR
    EMBODIED_PER_HOUR = extract_embodied_factors(load_embodied_raw())
    return len(EMBODIED_PER_HOUR)


reload_embodied_data()

# Constants

# Average CPU utilisation assumption (CCF default is 50%)
DEFAULT_CPU_UTILISATION = 0.50

# Hours in a month (730 is the standard billing month)
HOURS_PER_MONTH = 730

# Storage coefficients from CCF methodology (watt-hours per TB-hour)
SSD_COEFFICIENT = 1.2   # wh/TB-hour
HDD_COEFFICIENT = 0.65  # wh/TB-hour

# Baseline wattage for Elastic Load Balancers.
# AWS does not publish per-LB power data; these figures are conservative baselines
# consistent with the scale of a small-to-medium active load balancer.
# ALB operates at Layer 7 (HTTP/S) with SSL termination → higher overhead than NLB.
# NLB operates at Layer 4 (TCP/UDP) → more efficient.
ELB_WATTS = {
    "application": 8.0,   # Application Load Balancer baseline watts
    "network":     5.0,   # Network Load Balancer baseline watts
    "classic":     8.0,   # Classic Load Balancer baseline watts (similar to ALB)
    "gateway":     5.0,   # Gateway Load Balancer baseline watts
}


# Result dataclass

@dataclass
class CarbonEstimate:
    resource_type: str
    resource_id: str
    region: str
    instance_type: Optional[str]
    energy_kwh_month: float
    carbon_gco2e_month: float
    assumptions: dict
    embodied_gco2e_month: Optional[float] = None

    def summary(self) -> str:
        carbon = self.carbon_gco2e_month
        energy = self.energy_kwh_month
        if carbon > 1_000_000:
            carbon_str = f"{carbon / 1_000_000:.2f} tCO2e/month ({carbon * 12 / 1_000_000:.2f} tCO2e/year)"
        elif carbon > 1_000:
            carbon_str = f"{carbon / 1000:.2f} kgCO2e/month ({carbon * 12 / 1000:.2f} kgCO2e/year)"
        else:
            carbon_str = f"{carbon:.1f} gCO2e/month ({carbon * 12:.1f} gCO2e/year)"

        return (
            f"  {self.resource_id} ({self.resource_type})\n"
            f"    Region:   {self.region}\n"
            f"    Instance: {self.instance_type or 'N/A'}\n"
            f"    Energy:   {energy:.3f} kWh/month ({energy * 12:.3f} kWh/year)\n"
            f"    Carbon:   {carbon_str}\n"
            f"    Assumed:  CPU util={self.assumptions.get('cpu_utilisation', 'N/A')}, "
            f"PUE={self.assumptions.get('pue', 'N/A')}"
        )


# Estimation functions

def estimate_ec2(
    instance_type: str,
    region: str,
    resource_id: str = "unknown",
    cpu_utilisation: float = DEFAULT_CPU_UTILISATION,
    hours: float = HOURS_PER_MONTH,
) -> Optional[CarbonEstimate]:
    """
    Estimate carbon for an EC2 instance.

    The energy formula interpolates between idle (min_watts) and
    full load (max_watts) based on the assumed CPU utilisation.
    This mirrors the CCF approach exactly.
    """

    # Check we have data for this instance type
    if instance_type not in INSTANCE_WATTS:
        logger.warning("No wattage data for %s - skipping", instance_type)
        return None

    # Check we have grid intensity for this region
    if region not in GRID_INTENSITY:
        logger.warning("No grid intensity data for region %s - skipping", region)
        return None

    watts = INSTANCE_WATTS[instance_type]
    min_w = watts["min"]
    max_w = watts["max"]
    grid  = GRID_INTENSITY[region]

    # This is the CCF interpolation formula
    avg_watts = min_w + (cpu_utilisation * (max_w - min_w))

    # Divide by 1000 to go from Wh to kWh
    energy_kwh = (avg_watts * hours) / 1000
    energy_kwh_with_pue = energy_kwh * PUE

    # Grid intensity is in kgCO2e/kWh, multiply by 1000 for grams
    carbon_gco2e = energy_kwh_with_pue * grid * 1000
    embodied_gco2e = estimate_embodied(instance_type=instance_type, hours=hours)

    return CarbonEstimate(
        resource_type="aws_instance",
        resource_id=resource_id,
        region=region,
        instance_type=instance_type,
        energy_kwh_month=energy_kwh_with_pue,
        carbon_gco2e_month=carbon_gco2e,
        embodied_gco2e_month=embodied_gco2e,
        assumptions={
            "cpu_utilisation": cpu_utilisation,
            "pue": PUE,
            "min_watts": min_w,
            "max_watts": max_w,
            "avg_watts": round(avg_watts, 2),
            "grid_intensity_kgco2e_kwh": grid,
            "hours": hours,
        },
    )


def estimate_embodied(instance_type: str, hours: float = HOURS_PER_MONTH) -> Optional[float]:
    """
    Estimate monthly embodied carbon for an EC2 instance type in gCO2e.

    Boavizta's cloud instance endpoint returns embodied GWP already amortised
    to kgCO2e per hour for the instance type.
    """
    embodied_kgco2e_per_hour = EMBODIED_PER_HOUR.get(instance_type)
    if embodied_kgco2e_per_hour is None:
        return None
    return embodied_kgco2e_per_hour * hours * 1000


def estimate_ebs_storage(
    size_gb: float,
    volume_type: str,
    region: str,
    resource_id: str = "unknown",
    hours: float = HOURS_PER_MONTH,
) -> Optional[CarbonEstimate]:
    """
    Estimate carbon for an EBS volume.

    gp2/gp3/io1/io2 are SSD, st1/sc1 are HDD.
    Uses CCF storage coefficients.
    """

    if region not in GRID_INTENSITY:
        logger.warning("No grid intensity data for region %s - skipping", region)
        return None

    ssd_types = {"gp2", "gp3", "io1", "io2"}
    hdd_types  = {"st1", "sc1", "standard"}

    if volume_type in ssd_types:
        coeff = SSD_COEFFICIENT  # wh/TB-hour
    elif volume_type in hdd_types:
        coeff = HDD_COEFFICIENT
    else:
        # Default to SSD if unknown
        coeff = SSD_COEFFICIENT

    grid = GRID_INTENSITY[region]

    # Convert GB to TB, then calculate energy in wh, then kWh
    size_tb      = size_gb / 1000
    energy_wh    = size_tb * coeff * hours
    energy_kwh   = energy_wh / 1000
    energy_kwh_with_pue = energy_kwh * PUE

    carbon_gco2e = energy_kwh_with_pue * grid * 1000

    return CarbonEstimate(
        resource_type="aws_ebs_volume",
        resource_id=resource_id,
        region=region,
        instance_type=f"EBS {volume_type} {size_gb}GB",
        energy_kwh_month=energy_kwh_with_pue,
        carbon_gco2e_month=carbon_gco2e,
        assumptions={
            "volume_type": volume_type,
            "size_gb": size_gb,
            "coefficient_wh_per_tb_hr": coeff,
            "pue": PUE,
            "grid_intensity_kgco2e_kwh": grid,
        },
    )


def estimate_rds(
    instance_class: str,
    region: str,
    storage_gb: float = 0,
    storage_type: str = "gp2",
    resource_id: str = "unknown",
    cpu_utilisation: float = DEFAULT_CPU_UTILISATION,
    hours: float = HOURS_PER_MONTH,
) -> Optional[CarbonEstimate]:
    """
    Estimate carbon for an RDS instance (compute + storage).

    Compute energy uses the same CCF interpolation formula as EC2,
    using wattage data keyed by the db.* instance class.
    Storage energy uses the same SSD/HDD coefficients as EBS.
    Aurora and io1/io2/gp2/gp3 storage types are treated as SSD;
    magnetic storage is treated as HDD.
    """

    if region not in GRID_INTENSITY:
        logger.warning("No grid intensity data for region %s - skipping", region)
        return None

    grid = GRID_INTENSITY[region]

    # Compute energy 
    compute_energy_kwh = 0.0
    min_w = max_w = avg_watts = 0.0

    if instance_class in INSTANCE_WATTS:
        watts  = INSTANCE_WATTS[instance_class]
        min_w  = watts["min"]
        max_w  = watts["max"]
        avg_watts = min_w + (cpu_utilisation * (max_w - min_w))
        compute_energy_kwh = (avg_watts * hours) / 1000 * PUE
    else:
        logger.warning("No wattage data for %s - compute energy set to 0", instance_class)

    # Storage energy
    ssd_storage_types = {"gp2", "gp3", "io1", "io2", "aurora", "aurora-iopt1"}
    hdd_storage_types = {"magnetic"}

    if storage_type in ssd_storage_types:
        coeff = SSD_COEFFICIENT
    elif storage_type in hdd_storage_types:
        coeff = HDD_COEFFICIENT
    else:
        # Default to SSD for unknown types
        coeff = SSD_COEFFICIENT

    size_tb = storage_gb / 1000
    storage_energy_kwh = (size_tb * coeff * hours) / 1000 * PUE

    # Totals
    total_energy_kwh = compute_energy_kwh + storage_energy_kwh
    carbon_gco2e     = total_energy_kwh * grid * 1000

    return CarbonEstimate(
        resource_type="aws_db_instance",
        resource_id=resource_id,
        region=region,
        instance_type=instance_class,
        energy_kwh_month=total_energy_kwh,
        carbon_gco2e_month=carbon_gco2e,
        assumptions={
            "cpu_utilisation": cpu_utilisation,
            "pue": PUE,
            "min_watts": min_w,
            "max_watts": max_w,
            "avg_watts": round(avg_watts, 2),
            "compute_energy_kwh": round(compute_energy_kwh, 4),
            "storage_gb": storage_gb,
            "storage_type": storage_type,
            "storage_coefficient_wh_per_tb_hr": coeff,
            "storage_energy_kwh": round(storage_energy_kwh, 4),
            "grid_intensity_kgco2e_kwh": grid,
            "hours": hours,
        },
    )


def estimate_elb(
    lb_type: str,
    region: str,
    resource_id: str = "unknown",
    hours: float = HOURS_PER_MONTH,
) -> Optional[CarbonEstimate]:
    """
    Estimate carbon for an Elastic Load Balancer (ALB, NLB, CLB, or GWLB).

    AWS CCFT reports load balancer emissions under "AmazonEC2", so including
    ELBs in the audit brings our estimate closer to the CCFT figure.

    The energy model uses a fixed baseline wattage per load balancer type:
    ALB/CLB ≈ 8 W (Layer-7, SSL termination overhead)
    NLB/GWLB ≈ 5 W (Layer-4, more efficient)

    These are conservative baselines; actual consumption scales with traffic,
    but per-LB wattage data is not published by AWS.
    """

    if region not in GRID_INTENSITY:
        logger.warning("No grid intensity data for region %s - skipping", region)
        return None

    # Normalise the type string (boto3 returns lowercase for ELBv2)
    normalised_type = lb_type.lower()
    baseline_watts = ELB_WATTS.get(normalised_type, ELB_WATTS["application"])

    grid = GRID_INTENSITY[region]

    energy_kwh = (baseline_watts * hours) / 1000
    energy_kwh_with_pue = energy_kwh * PUE
    carbon_gco2e = energy_kwh_with_pue * grid * 1000

    return CarbonEstimate(
        resource_type="aws_lb",
        resource_id=resource_id,
        region=region,
        instance_type=f"ELB ({lb_type})",
        energy_kwh_month=energy_kwh_with_pue,
        carbon_gco2e_month=carbon_gco2e,
        embodied_gco2e_month=None,
        assumptions={
            "lb_type": lb_type,
            "baseline_watts": baseline_watts,
            "pue": PUE,
            "grid_intensity_kgco2e_kwh": grid,
            "hours": hours,
        },
    )


def print_summary(estimates: list[CarbonEstimate], title: str = "Carbon Estimate Summary"):
    """Print a readable summary of all estimates."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

    if not estimates:
        print("  No estimates produced.")
        return

    total_carbon = sum(e.carbon_gco2e_month for e in estimates)
    total_energy = sum(e.energy_kwh_month for e in estimates)

    for e in estimates:
        print(e.summary())
        print()

    print(f"{'─'*60}")
    print(f"  TOTAL Energy:  {total_energy:.3f} kWh/month ({total_energy * 12:.3f} kWh/year)")

    if total_carbon > 1_000_000:
        print(f"  TOTAL Carbon:  {total_carbon / 1_000_000:.3f} tCO2e/month ({total_carbon * 12 / 1_000_000:.3f} tCO2e/year)")
    elif total_carbon > 1_000:
        print(f"  TOTAL Carbon:  {total_carbon / 1000:.2f} kgCO2e/month ({total_carbon * 12 / 1000:.2f} kgCO2e/year)")
    else:
        print(f"  TOTAL Carbon:  {total_carbon:.1f} gCO2e/month ({total_carbon * 12:.1f} gCO2e/year)")

    print()
    print("  ⚠  These are directional estimates based on assumed 50% CPU")
    print("     utilisation. Actual usage will vary. Validate against AWS")
    print("     Customer Carbon Footprint Tool once resources are live.")
    print(f"{'='*60}\n")
