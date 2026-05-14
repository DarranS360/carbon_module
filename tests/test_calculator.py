"""
tests/test_calculator.py

Unit tests for calculator.py (Core Carbon Estimation Engine).

Each test verifies a specific function against a hand-calculated expected value,
ensuring that if a bug were introduced the test would catch it.
"""

import pytest
import sys
import os

# Ensure the repo root is on the path so calculator can be imported directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from calculator import (
    estimate_ec2,
    estimate_ebs_storage,
    estimate_rds,
    estimate_embodied,
    estimate_elb,
    INSTANCE_WATTS,
    GRID_INTENSITY,
    PUE,
    SSD_COEFFICIENT,
    HDD_COEFFICIENT,
    ELB_WATTS,
    DEFAULT_CPU_UTILISATION,
    HOURS_PER_MONTH,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _expected_ec2_carbon(instance_type: str, region: str, cpu_util: float = DEFAULT_CPU_UTILISATION, hours: float = HOURS_PER_MONTH) -> float:
    """Hand-calculate the expected carbon value for an EC2 instance."""
    w = INSTANCE_WATTS[instance_type]
    avg_watts = w["min"] + (cpu_util * (w["max"] - w["min"]))
    energy_kwh = (avg_watts * hours) / 1000 * PUE
    return energy_kwh * GRID_INTENSITY[region] * 1000


def _expected_ebs_carbon(size_gb: float, region: str, coeff: float, hours: float = HOURS_PER_MONTH) -> float:
    """Hand-calculate the expected carbon value for an EBS volume."""
    size_tb = size_gb / 1000
    energy_kwh = (size_tb * coeff * hours) / 1000 * PUE
    return energy_kwh * GRID_INTENSITY[region] * 1000


# ── estimate_ec2 ──────────────────────────────────────────────────────────────

class TestEstimateEC2:
    """Tests for the estimate_ec2() function."""

    def test_known_instance_and_region_returns_estimate(self):
        """A known instance type in a known region should return a CarbonEstimate."""
        result = estimate_ec2("t3.medium", "eu-west-1")
        assert result is not None

    def test_energy_value_matches_formula(self):
        """Energy output must match the CCF interpolation formula exactly."""
        instance_type = "t3.medium"
        region = "eu-west-1"
        result = estimate_ec2(instance_type, region)

        w = INSTANCE_WATTS[instance_type]
        avg_watts = w["min"] + (DEFAULT_CPU_UTILISATION * (w["max"] - w["min"]))
        expected_energy = (avg_watts * HOURS_PER_MONTH) / 1000 * PUE

        assert result.energy_kwh_month == pytest.approx(expected_energy, rel=1e-6)

    def test_carbon_value_matches_formula(self):
        """Carbon output must equal energy × grid intensity × 1000."""
        instance_type = "t3.medium"
        region = "eu-west-1"
        result = estimate_ec2(instance_type, region)

        expected_carbon = _expected_ec2_carbon(instance_type, region)
        assert result.carbon_gco2e_month == pytest.approx(expected_carbon, rel=1e-6)

    def test_different_region_uses_different_grid_intensity(self):
        """Carbon estimates for the same instance in different regions must differ."""
        result_eu = estimate_ec2("m5.large", "eu-west-1")
        result_us = estimate_ec2("m5.large", "us-east-1")

        assert result_eu is not None
        assert result_us is not None
        assert result_eu.carbon_gco2e_month != result_us.carbon_gco2e_month

    def test_unknown_instance_type_returns_none(self):
        """An unrecognised instance type should return None (not raise)."""
        result = estimate_ec2("xx99.unknown", "eu-west-1")
        assert result is None

    def test_unknown_region_returns_none(self):
        """An unrecognised region should return None (not raise)."""
        result = estimate_ec2("t3.medium", "xx-nowhere-99")
        assert result is None

    def test_result_metadata_is_correct(self):
        """resource_type, region, and instance_type fields must be populated correctly."""
        result = estimate_ec2("c5.large", "us-east-1", resource_id="my-server")
        assert result.resource_type == "aws_instance"
        assert result.region == "us-east-1"
        assert result.instance_type == "c5.large"
        assert result.assumptions["cpu_utilisation"] == DEFAULT_CPU_UTILISATION

    def test_carbon_is_in_correct_order_of_magnitude(self):
        """
        Grid intensity values are in kgCO2e/kWh (NOT mtCO2e/kWh).
        A t3.medium at 50% CPU in eu-west-1 running 730 hours should produce
        roughly 500–5000 gCO2e/month (0.5–5 kgCO2e), not <10 gCO2e.
        This test guards against the grid intensity unit being off by 1000x.
        """
        result = estimate_ec2("t3.medium", "eu-west-1")
        assert result is not None
        # With eu-west-1 grid ≈ 0.305 kgCO2e/kWh and ~4 kWh/month energy:
        # expected ≈ 4 * 0.305 * 1000 ≈ 1220 gCO2e. Sanity bounds: 100–10000 gCO2e.
        assert result.carbon_gco2e_month > 100, (
            f"carbon {result.carbon_gco2e_month:.3f} gCO2e is suspiciously low "
            "(grid intensity may be in wrong units — should be kgCO2e/kWh)"
        )
        assert result.carbon_gco2e_month < 10_000, (
            f"carbon {result.carbon_gco2e_month:.3f} gCO2e is suspiciously high"
        )


# ── estimate_ebs_storage ──────────────────────────────────────────────────────

class TestEstimateEBSStorage:
    """Tests for the estimate_ebs_storage() function."""

    def test_ssd_volume_uses_ssd_coefficient(self):
        """gp2 volumes should use the SSD coefficient (1.2 wh/TB-hr)."""
        result = estimate_ebs_storage(100, "gp2", "eu-west-1")
        expected_carbon = _expected_ebs_carbon(100, "eu-west-1", SSD_COEFFICIENT)
        assert result is not None
        assert result.carbon_gco2e_month == pytest.approx(expected_carbon, rel=1e-6)
        assert result.assumptions["coefficient_wh_per_tb_hr"] == SSD_COEFFICIENT

    def test_hdd_volume_uses_hdd_coefficient(self):
        """st1 volumes should use the HDD coefficient (0.65 wh/TB-hr)."""
        result = estimate_ebs_storage(100, "st1", "eu-west-1")
        expected_carbon = _expected_ebs_carbon(100, "eu-west-1", HDD_COEFFICIENT)
        assert result is not None
        assert result.carbon_gco2e_month == pytest.approx(expected_carbon, rel=1e-6)
        assert result.assumptions["coefficient_wh_per_tb_hr"] == HDD_COEFFICIENT

    def test_ssd_carbon_higher_than_hdd_for_same_size(self):
        """SSD storage should produce more carbon than HDD for identical capacity."""
        ssd = estimate_ebs_storage(500, "gp2", "eu-west-1")
        hdd = estimate_ebs_storage(500, "st1", "eu-west-1")
        assert ssd.carbon_gco2e_month > hdd.carbon_gco2e_month

    def test_gp3_treated_as_ssd(self):
        """gp3 is an SSD type and must use the SSD coefficient."""
        result = estimate_ebs_storage(200, "gp3", "eu-west-1")
        expected_carbon = _expected_ebs_carbon(200, "eu-west-1", SSD_COEFFICIENT)
        assert result.carbon_gco2e_month == pytest.approx(expected_carbon, rel=1e-6)

    def test_unknown_region_returns_none(self):
        """An unrecognised region should return None."""
        result = estimate_ebs_storage(100, "gp2", "xx-nowhere-99")
        assert result is None

    def test_result_resource_type(self):
        """resource_type must be 'aws_ebs_volume'."""
        result = estimate_ebs_storage(50, "gp2", "us-east-1")
        assert result.resource_type == "aws_ebs_volume"


# ── estimate_rds ──────────────────────────────────────────────────────────────

class TestEstimateRDS:
    """Tests for the estimate_rds() function."""

    def test_known_class_and_region_returns_estimate(self):
        """A known RDS instance class in a known region should return a CarbonEstimate."""
        result = estimate_rds("db.t3.medium", "eu-west-1", storage_gb=100)
        assert result is not None

    def test_compute_and_storage_components_add_to_total(self):
        """Total energy must be close to the sum of compute and storage components.

        The assumptions dict stores rounded (4 d.p.) values, so we allow a small
        absolute tolerance to accommodate rounding artefacts.
        """
        result = estimate_rds("db.t3.medium", "eu-west-1", storage_gb=100)
        compute = result.assumptions["compute_energy_kwh"]
        storage = result.assumptions["storage_energy_kwh"]
        assert result.energy_kwh_month == pytest.approx(compute + storage, abs=1e-3)

    def test_carbon_equals_total_energy_times_grid(self):
        """Carbon output must equal total_energy × grid_intensity × 1000."""
        result = estimate_rds("db.m5.large", "us-east-1", storage_gb=50)
        expected_carbon = result.energy_kwh_month * GRID_INTENSITY["us-east-1"] * 1000
        assert result.carbon_gco2e_month == pytest.approx(expected_carbon, rel=1e-6)

    def test_hdd_storage_type_uses_hdd_coefficient(self):
        """RDS magnetic storage should use the HDD coefficient."""
        result = estimate_rds("db.t3.medium", "eu-west-1", storage_gb=100, storage_type="magnetic")
        assert result.assumptions["storage_coefficient_wh_per_tb_hr"] == HDD_COEFFICIENT

    def test_unknown_region_returns_none(self):
        """An unrecognised region should return None."""
        result = estimate_rds("db.t3.medium", "xx-nowhere-99", storage_gb=50)
        assert result is None

    def test_unknown_instance_class_still_returns_estimate(self):
        """
        An unknown RDS instance class should still produce an estimate —
        compute energy defaults to 0 but storage is still calculated.
        """
        result = estimate_rds("db.xx99.unknown", "eu-west-1", storage_gb=100)
        assert result is not None
        assert result.assumptions["compute_energy_kwh"] == 0.0

    def test_result_resource_type(self):
        """resource_type must be 'aws_db_instance'."""
        result = estimate_rds("db.t3.medium", "eu-west-1")
        assert result.resource_type == "aws_db_instance"


# ── estimate_embodied ─────────────────────────────────────────────────────────

class TestEstimateEmbodied:
    """Tests for the estimate_embodied() function."""

    def test_known_instance_returns_float(self):
        """
        For any instance type present in the Boavizta lookup table,
        estimate_embodied should return a positive float.
        """
        from calculator import EMBODIED_PER_HOUR
        if not EMBODIED_PER_HOUR:
            pytest.skip("Embodied data not loaded — skipping embodied tests")

        instance_type = next(iter(EMBODIED_PER_HOUR))
        result = estimate_embodied(instance_type)
        assert result is not None
        assert result > 0.0

    def test_value_scales_with_hours(self):
        """Embodied carbon should scale linearly with the number of hours."""
        from calculator import EMBODIED_PER_HOUR
        if not EMBODIED_PER_HOUR:
            pytest.skip("Embodied data not loaded — skipping embodied tests")

        instance_type = next(iter(EMBODIED_PER_HOUR))
        result_1h = estimate_embodied(instance_type, hours=1)
        result_2h = estimate_embodied(instance_type, hours=2)
        assert result_2h == pytest.approx(result_1h * 2, rel=1e-6)

    def test_unknown_instance_returns_none(self):
        """An instance type absent from the Boavizta table should return None."""
        result = estimate_embodied("xx99.definitely-not-real")
        assert result is None


# ── estimate_elb ──────────────────────────────────────────────────────────────

class TestEstimateELB:
    """Tests for the estimate_elb() function."""

    def test_alb_returns_estimate(self):
        """An ALB in a known region should return a CarbonEstimate."""
        result = estimate_elb("application", "eu-west-1")
        assert result is not None

    def test_nlb_returns_estimate(self):
        """An NLB in a known region should return a CarbonEstimate."""
        result = estimate_elb("network", "eu-west-1")
        assert result is not None

    def test_alb_energy_matches_formula(self):
        """ALB energy must equal (baseline_watts * hours / 1000) * PUE."""
        result = estimate_elb("application", "eu-west-1")
        expected_energy = (ELB_WATTS["application"] * HOURS_PER_MONTH / 1000) * PUE
        assert result.energy_kwh_month == pytest.approx(expected_energy, rel=1e-6)

    def test_alb_carbon_matches_formula(self):
        """ALB carbon must equal energy_kwh * grid_intensity * 1000."""
        result = estimate_elb("application", "eu-west-1")
        expected_energy = (ELB_WATTS["application"] * HOURS_PER_MONTH / 1000) * PUE
        expected_carbon = expected_energy * GRID_INTENSITY["eu-west-1"] * 1000
        assert result.carbon_gco2e_month == pytest.approx(expected_carbon, rel=1e-6)

    def test_nlb_lower_carbon_than_alb(self):
        """NLB should produce lower carbon than ALB (lower baseline wattage)."""
        alb = estimate_elb("application", "eu-west-1")
        nlb = estimate_elb("network", "eu-west-1")
        assert nlb.carbon_gco2e_month < alb.carbon_gco2e_month

    def test_different_regions_give_different_carbon(self):
        """Same ELB type in different regions must give different carbon."""
        result_eu = estimate_elb("application", "eu-west-1")
        result_us = estimate_elb("application", "us-east-1")
        assert result_eu.carbon_gco2e_month != result_us.carbon_gco2e_month

    def test_unknown_region_returns_none(self):
        """An unrecognised region should return None."""
        result = estimate_elb("application", "xx-nowhere-99")
        assert result is None

    def test_result_resource_type(self):
        """resource_type must be 'aws_lb'."""
        result = estimate_elb("application", "eu-west-1")
        assert result.resource_type == "aws_lb"

    def test_embodied_is_none(self):
        """ELBs have no embodied carbon data, so embodied_gco2e_month must be None."""
        result = estimate_elb("network", "us-east-1")
        assert result.embodied_gco2e_month is None

    def test_unknown_type_falls_back_to_alb_baseline(self):
        """An unrecognised LB type should fall back to the ALB baseline wattage."""
        result = estimate_elb("unknown_type", "eu-west-1")
        result_alb = estimate_elb("application", "eu-west-1")
        assert result is not None
        assert result.energy_kwh_month == pytest.approx(result_alb.energy_kwh_month, rel=1e-6)
        assert result.assumptions["baseline_watts"] == ELB_WATTS["application"]
