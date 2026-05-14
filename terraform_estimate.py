"""
terraform_estimate.py

Parses a Terraform plan JSON file and estimates the carbon footprint
of resources before they are provisioned.

Usage:
    python terraform_estimate.py path/to/plan.json

To generate a real plan.json from your own Terraform:
    terraform plan -out=tfplan
    terraform show -json tfplan > plan.json
    python terraform_estimate.py plan.json
"""

import json
import logging
import sys
import os
from calculator import estimate_ec2, estimate_ebs_storage, estimate_rds, print_summary
from cost_calculator import estimate_ec2_cost, estimate_ebs_cost, estimate_rds_cost, print_cost_summary

logger = logging.getLogger(__name__)


def extract_region_from_plan(plan: dict) -> str:
    """
    Pull the AWS region from the provider configuration block.
    """
    try:
        provider_config = plan.get("configuration", {}).get("provider_config", {})
        aws_config = provider_config.get("aws", {})
        expressions = aws_config.get("expressions", {})
        region_expr = expressions.get("region", {})

        # Terraform plan JSON stores static values as constant_value
        region = region_expr.get("constant_value")
        if region:
            return region
    except (KeyError, TypeError):
        pass

    logger.warning("Could not determine region from provider config, defaulting to eu-west-1")
    return "eu-west-1"


def az_to_region(availability_zone: str) -> str:
    """
    Convert an availability zone like 'eu-west-1a' to a region 'eu-west-1'.
    AZs are just the region with a letter suffix.
    """
    if not availability_zone:
        return None
    # Strip the trailing letter (a/b/c/d)
    # e.g. eu-west-1a -> eu-west-1
    parts = availability_zone.split("-")
    if len(parts) >= 3:
        last = parts[-1]
        # If last part ends in a letter, strip it
        if last and last[-1].isalpha() and last[:-1].isdigit():
            parts[-1] = last[:-1]
    return "-".join(parts)


def parse_and_estimate(plan_path: str):
    """
    Main function: load the plan, walk resource_changes,
    and produce a carbon estimate for each resource being created.

    Note: only estimate resources with action "create".
    Updates and deletes are not relevant for prospective estimation.
    """

    print(f"\nLoading Terraform plan from: {plan_path}")

    with open(plan_path) as f:
        plan = json.load(f)

    # Get the provider-level region as a fallback
    provider_region = extract_region_from_plan(plan)
    print(f"Provider region: {provider_region}")

    resource_changes = plan.get("resource_changes", [])
    print(f"Found {len(resource_changes)} resource change(s) in plan\n")

    estimates      = []
    cost_estimates = []
    skipped        = []

    for resource in resource_changes:
        change  = resource.get("change", {})
        actions = change.get("actions", [])

        if "create" not in actions:
            print(f"  Skipping {resource['address']} (action: {actions})")
            continue

        resource_type    = resource.get("type")
        resource_address = resource.get("address")
        after_values     = change.get("after", {})

        print(f"  Processing: {resource_address}")

        # EC2 Instances 
        if resource_type == "aws_instance":
            instance_type = after_values.get("instance_type")
            az            = after_values.get("availability_zone")
            region        = az_to_region(az) if az else provider_region

            if not instance_type:
                print(f"    [WARN] No instance_type found, skipping")
                skipped.append(resource_address)
                continue

            print(f"    → EC2 {instance_type} in {region}")
            est = estimate_ec2(
                instance_type=instance_type,
                region=region,
                resource_id=resource_address,
            )
            if est:
                estimates.append(est)
            else:
                skipped.append(resource_address)

            cost_est = estimate_ec2_cost(
                instance_type=instance_type,
                region=region,
                resource_id=resource_address,
            )
            if cost_est:
                cost_estimates.append(cost_est)

        # RDS Instances
        elif resource_type == "aws_db_instance":
            instance_class = after_values.get("instance_class")
            az             = after_values.get("availability_zone")
            region         = az_to_region(az) if az else provider_region
            storage_gb     = after_values.get("allocated_storage", 0)
            storage_type   = after_values.get("storage_type", "gp2")

            if not instance_class:
                print(f"    [WARN] No instance_class found, skipping")
                skipped.append(resource_address)
                continue

            print(f"    → RDS {instance_class} {storage_gb}GB ({storage_type}) in {region}")
            est = estimate_rds(
                instance_class=instance_class,
                region=region,
                storage_gb=storage_gb,
                storage_type=storage_type,
                resource_id=resource_address,
            )
            if est:
                estimates.append(est)
            else:
                skipped.append(resource_address)

            engine   = after_values.get("engine", "mysql")
            multi_az = after_values.get("multi_az", False)
            cost_est = estimate_rds_cost(
                instance_class=instance_class,
                region=region,
                storage_gb=storage_gb,
                storage_type=storage_type,
                engine=engine,
                multi_az=multi_az,
                resource_id=resource_address,
            )
            if cost_est:
                cost_estimates.append(cost_est)

        # EBS Volumes
        elif resource_type == "aws_ebs_volume":
            az          = after_values.get("availability_zone")
            region      = az_to_region(az) if az else provider_region
            size_gb     = after_values.get("size", 0)
            volume_type = after_values.get("type", "gp2")

            print(f"    → EBS {volume_type} {size_gb}GB in {region}")
            est = estimate_ebs_storage(
                size_gb=size_gb,
                volume_type=volume_type,
                region=region,
                resource_id=resource_address,
            )
            if est:
                estimates.append(est)
            else:
                skipped.append(resource_address)

            cost_est = estimate_ebs_cost(
                size_gb=size_gb,
                volume_type=volume_type,
                region=region,
                resource_id=resource_address,
            )
            if cost_est:
                cost_estimates.append(cost_est)

        # Unsupported resource types
        else:
            print(f"    → Resource type '{resource_type}' not yet supported, skipping")
            skipped.append(resource_address)

    # Print results
    print_summary(estimates, title="Pre-Provisioning Carbon Estimate (Terraform Plan)")
    print_cost_summary(cost_estimates, title="Pre-Provisioning Cost Estimate (Terraform Plan)")

    if skipped:
        print(f"  Skipped {len(skipped)} resource(s): {', '.join(skipped)}")
        print()


def estimate_from_plan_dict(plan: dict) -> dict:
    """
    Accept a Terraform plan dict, walk resource_changes, and return
    carbon + cost estimates for each resource being created.

    Returns a dict with:
      - resources: list of per-resource estimates (carbon + cost)
      - totals: aggregated carbon and cost totals
      - skipped: list of resource addresses that could not be estimated
    """
    provider_region = extract_region_from_plan(plan)
    resource_changes = plan.get("resource_changes", [])

    resources = []
    skipped = []

    for resource in resource_changes:
        change = resource.get("change", {})
        actions = change.get("actions", [])

        if "create" not in actions:
            continue

        resource_type = resource.get("type")
        resource_address = resource.get("address")
        after_values = change.get("after", {})

        carbon_est = None
        cost_est = None

        # EC2 Instances
        if resource_type == "aws_instance":
            instance_type = after_values.get("instance_type")
            az = after_values.get("availability_zone")
            region = az_to_region(az) if az else provider_region

            if not instance_type:
                skipped.append(resource_address)
                continue

            carbon_est = estimate_ec2(
                instance_type=instance_type,
                region=region,
                resource_id=resource_address,
            )
            cost_est = estimate_ec2_cost(
                instance_type=instance_type,
                region=region,
                resource_id=resource_address,
            )

        # RDS Instances
        elif resource_type == "aws_db_instance":
            instance_class = after_values.get("instance_class")
            az = after_values.get("availability_zone")
            region = az_to_region(az) if az else provider_region
            storage_gb = after_values.get("allocated_storage", 0)
            storage_type = after_values.get("storage_type", "gp2")
            engine = after_values.get("engine", "mysql")
            multi_az = after_values.get("multi_az", False)

            if not instance_class:
                skipped.append(resource_address)
                continue

            carbon_est = estimate_rds(
                instance_class=instance_class,
                region=region,
                storage_gb=storage_gb,
                storage_type=storage_type,
                resource_id=resource_address,
            )
            cost_est = estimate_rds_cost(
                instance_class=instance_class,
                region=region,
                storage_gb=storage_gb,
                storage_type=storage_type,
                engine=engine,
                multi_az=multi_az,
                resource_id=resource_address,
            )

        # EBS Volumes
        elif resource_type == "aws_ebs_volume":
            az = after_values.get("availability_zone")
            region = az_to_region(az) if az else provider_region
            size_gb = after_values.get("size", 0)
            volume_type = after_values.get("type", "gp2")

            carbon_est = estimate_ebs_storage(
                size_gb=size_gb,
                volume_type=volume_type,
                region=region,
                resource_id=resource_address,
            )
            cost_est = estimate_ebs_cost(
                size_gb=size_gb,
                volume_type=volume_type,
                region=region,
                resource_id=resource_address,
            )

        # Unsupported resource types
        else:
            skipped.append(resource_address)
            continue

        if carbon_est is None:
            skipped.append(resource_address)
            continue

        resources.append({
            "address": resource_address,
            "resource_type": resource_type,
            "region": carbon_est.region,
            "carbon": {
                "energy_kwh_month": round(carbon_est.energy_kwh_month, 4),
                "carbon_gco2e_month": round(carbon_est.carbon_gco2e_month, 4),
                "embodied_gco2e_month": (
                    round(carbon_est.embodied_gco2e_month, 4)
                    if carbon_est.embodied_gco2e_month is not None
                    else None
                ),
                "assumptions": carbon_est.assumptions,
            },
            "cost": {
                "cost_usd_month": round(cost_est.cost_usd_month, 4),
                "pricing_details": cost_est.pricing_details,
            } if cost_est is not None else None,
        })

    total_carbon = sum(r["carbon"]["carbon_gco2e_month"] for r in resources)
    embodied_values = [
        r["carbon"]["embodied_gco2e_month"]
        for r in resources
        if r["carbon"]["embodied_gco2e_month"] is not None
    ]
    total_embodied = sum(embodied_values) if embodied_values else None
    total_energy = sum(r["carbon"]["energy_kwh_month"] for r in resources)
    total_cost = sum(
        r["cost"]["cost_usd_month"] for r in resources if r["cost"] is not None
    )

    return {
        "resources": resources,
        "totals": {
            "energy_kwh_month": round(total_energy, 4),
            "carbon_gco2e_month": round(total_carbon, 4),
            "embodied_gco2e_month": round(total_embodied, 4) if total_embodied is not None else None,
            "cost_usd_month": round(total_cost, 4),
        },
        "skipped": skipped,
    }


if __name__ == "__main__":
    # Accept plan path as argument, default to the example
    if len(sys.argv) > 1:
        plan_path = sys.argv[1]
    else:
        plan_path = os.path.join(
            os.path.dirname(__file__), "terraform_example", "plan.json"
        )

    if not os.path.exists(plan_path):
        print(f"Error: plan file not found at {plan_path}")
        sys.exit(1)

    parse_and_estimate(plan_path)
