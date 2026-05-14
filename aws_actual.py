"""
aws_actual.py

Scansrunning AWS infrastructure using boto3 and estimates
the current carbon footprint of what's already deployed.

This is the validation side of the project - compare these estimates
against AWS Customer Carbon Footprint Tool (CCFT) to evaluate accuracy.

Requirements:
    pip install boto3
    AWS credentials configured (aws configure, env vars, or IAM role)

Usage:
    python aws_actual.py                          # uses default AWS profile/region
    python aws_actual.py --region eu-west-1       # specific region
    python aws_actual.py --profile my-profile     # specific AWS profile
    python aws_actual.py --all-regions            # scan all regions (slow)
"""

import argparse
import sys

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("Error: boto3 not installed. Run: pip install boto3")
    sys.exit(1)

from calculator import estimate_ec2, estimate_ebs_storage, estimate_rds, estimate_elb, print_summary
from cost_calculator import estimate_ec2_cost, estimate_ebs_cost, estimate_rds_cost, estimate_elb_cost


# Regions to scan 

SUPPORTED_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "ca-central-1",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1",
    "eu-north-1", "eu-south-1",
    "ap-east-1", "ap-southeast-1", "ap-southeast-2",
    "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
    "ap-south-1", "sa-east-1", "me-south-1", "af-south-1",
]


# EC2 scanning 

def scan_ec2_instances(region: str, session: boto3.Session) -> list:
    """
    List all running EC2 instances in a region and estimate their carbon.
    Only includes 'running' state - stopped instances don't consume CPU.
    """
    estimates = []

    try:
        ec2 = session.client("ec2", region_name=region)
        paginator = ec2.get_paginator("describe_instances")

        # Filter to running instances only
        pages = paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )

        instance_count = 0
        for page in pages:
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_id   = instance["InstanceId"]
                    instance_type = instance["InstanceType"]

                    # Get a name from tags if available
                    tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
                    name = tags.get("Name", instance_id)
                    display_id = f"{name} ({instance_id})"

                    print(f"    → EC2 {instance_type} [{display_id}]")
                    instance_count += 1

                    est = estimate_ec2(
                        instance_type=instance_type,
                        region=region,
                        resource_id=display_id,
                    )
                    if est:
                        estimates.append(est)

        if instance_count == 0:
            print(f"    No running EC2 instances found in {region}")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("UnauthorizedOperation", "AccessDenied"):
            print(f"    [WARN] No EC2 access in {region}: {error_code}")
        else:
            print(f"    [ERROR] EC2 scan failed in {region}: {e}")

    return estimates


# RDS scanning

def scan_rds_instances(region: str, session: boto3.Session) -> list:
    """
    List all available RDS instances in a region and estimate their carbon.
    Only includes instances in 'available' state.
    """
    estimates = []

    try:
        rds = session.client("rds", region_name=region)
        paginator = rds.get_paginator("describe_db_instances")
        pages = paginator.paginate()

        instance_count = 0
        for page in pages:
            for db in page["DBInstances"]:
                status = db.get("DBInstanceStatus", "")
                if status != "available":
                    continue

                db_id          = db["DBInstanceIdentifier"]
                instance_class = db["DBInstanceClass"]
                storage_gb     = db.get("AllocatedStorage", 0)
                storage_type   = db.get("StorageType", "gp2")

                print(f"    → RDS {instance_class} {storage_gb}GB ({storage_type}) [{db_id}]")
                instance_count += 1

                est = estimate_rds(
                    instance_class=instance_class,
                    region=region,
                    storage_gb=storage_gb,
                    storage_type=storage_type,
                    resource_id=db_id,
                )
                if est:
                    estimates.append(est)

        if instance_count == 0:
            print(f"    No available RDS instances found in {region}")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("UnauthorizedOperation", "AccessDenied"):
            print(f"    [WARN] No RDS access in {region}: {error_code}")
        else:
            print(f"    [ERROR] RDS scan failed in {region}: {e}")

    return estimates


# EBS scanning

def scan_ebs_volumes(region: str, session: boto3.Session) -> list:
    """
    List all in-use EBS volumes in a region and estimate their carbon.
    Only 'in-use' volumes are included (attached to running instances).
    """
    estimates = []

    try:
        ec2 = session.client("ec2", region_name=region)
        paginator = ec2.get_paginator("describe_volumes")

        # Only count volumes actually attached to instances
        pages = paginator.paginate(
            Filters=[{"Name": "status", "Values": ["in-use"]}]
        )

        volume_count = 0
        for page in pages:
            for volume in page["Volumes"]:
                volume_id   = volume["VolumeId"]
                size_gb     = volume["Size"]
                volume_type = volume["VolumeType"]
                az          = volume["AvailabilityZone"]

                tags = {t["Key"]: t["Value"] for t in volume.get("Tags", [])}
                name = tags.get("Name", volume_id)
                display_id = f"{name} ({volume_id})"

                print(f"    → EBS {volume_type} {size_gb}GB [{display_id}]")
                volume_count += 1

                est = estimate_ebs_storage(
                    size_gb=size_gb,
                    volume_type=volume_type,
                    region=region,
                    resource_id=display_id,
                )
                if est:
                    estimates.append(est)

        if volume_count == 0:
            print(f"    No in-use EBS volumes found in {region}")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("UnauthorizedOperation", "AccessDenied"):
            print(f"    [WARN] No EBS access in {region}: {error_code}")
        else:
            print(f"    [ERROR] EBS scan failed in {region}: {e}")

    return estimates


# ELB scanning 

def _elb_display_id(lb: dict) -> str:
    """Return a human-readable display ID for an ELBv2 load balancer dict.

    Format: ``<name> (<unique-id>)`` — mirrors the pattern used for EC2 and EBS.
    The unique ID is the last segment of the ARN (e.g. ``1234567890abcdef``).
    """
    lb_arn  = lb["LoadBalancerArn"]
    lb_name = lb.get("LoadBalancerName", lb_arn)
    return f"{lb_name} ({lb_arn.split('/')[-1]})"


def scan_elbs(region: str, session: boto3.Session) -> list:
    """
    List all active Elastic Load Balancers in a region and estimate their carbon.

    AWS CCFT attributes ELB emissions to the "AmazonEC2" service category,
    so including ELBs narrows the gap between our estimate and the CCFT figure.

    Only provisioned (active) load balancers are included; those in
    'provisioning' or 'failed' state are skipped.
    """
    estimates = []

    try:
        elbv2 = session.client("elbv2", region_name=region)
        paginator = elbv2.get_paginator("describe_load_balancers")
        pages = paginator.paginate()

        lb_count = 0
        for page in pages:
            for lb in page["LoadBalancers"]:
                state = lb.get("State", {}).get("Code", "")
                if state not in ("active", "active_impaired"):
                    continue

                lb_type    = lb.get("Type", "application")
                display_id = _elb_display_id(lb)

                print(f"    → ELB {lb_type} [{display_id}]")
                lb_count += 1

                est = estimate_elb(
                    lb_type=lb_type,
                    region=region,
                    resource_id=display_id,
                )
                if est:
                    estimates.append(est)

        if lb_count == 0:
            print(f"    No active load balancers found in {region}")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("UnauthorizedOperation", "AccessDenied"):
            print(f"    [WARN] No ELB access in {region}: {error_code}")
        else:
            print(f"    [ERROR] ELB scan failed in {region}: {e}")

    return estimates


# Combined live scan

def estimate_from_live(
    region: str,
    session: "boto3.Session",
    cpu_utilisation: float = 0.50,
) -> dict:
    """
    Scan running AWS infrastructure in *region* and return carbon + cost
    estimates in the same dict format as
    ``terraform_estimate.estimate_from_plan_dict``:

    .. code-block:: python

        {
            "resources": [...],   # per-resource carbon + cost dicts
            "totals":    {...},   # summed energy / carbon / cost
            "skipped":   [...],  # resource IDs that could not be estimated
        }
    """
    resources = []
    skipped = []

    # EC2 instances 
    try:
        ec2_client = session.client("ec2", region_name=region)
        paginator = ec2_client.get_paginator("describe_instances")
        pages = paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )

        for page in pages:
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_id   = instance["InstanceId"]
                    instance_type = instance["InstanceType"]

                    tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
                    name = tags.get("Name", instance_id)
                    display_id = f"{name} ({instance_id})"

                    carbon_est = estimate_ec2(
                        instance_type=instance_type,
                        region=region,
                        resource_id=display_id,
                        cpu_utilisation=cpu_utilisation,
                    )
                    cost_est = estimate_ec2_cost(
                        instance_type=instance_type,
                        region=region,
                        resource_id=display_id,
                    )

                    if carbon_est is None:
                        skipped.append(display_id)
                        continue

                    resources.append({
                        "address": display_id,
                        "resource_type": "aws_instance",
                        "region": region,
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

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code not in ("UnauthorizedOperation", "AccessDenied"):
            raise

    # EBS volumes
    try:
        ec2_client = session.client("ec2", region_name=region)
        paginator = ec2_client.get_paginator("describe_volumes")
        pages = paginator.paginate(
            Filters=[{"Name": "status", "Values": ["in-use"]}]
        )

        for page in pages:
            for volume in page["Volumes"]:
                volume_id   = volume["VolumeId"]
                size_gb     = volume["Size"]
                volume_type = volume["VolumeType"]

                tags = {t["Key"]: t["Value"] for t in volume.get("Tags", [])}
                name = tags.get("Name", volume_id)
                display_id = f"{name} ({volume_id})"

                carbon_est = estimate_ebs_storage(
                    size_gb=size_gb,
                    volume_type=volume_type,
                    region=region,
                    resource_id=display_id,
                )
                cost_est = estimate_ebs_cost(
                    size_gb=size_gb,
                    volume_type=volume_type,
                    region=region,
                    resource_id=display_id,
                )

                if carbon_est is None:
                    skipped.append(display_id)
                    continue

                resources.append({
                    "address": display_id,
                    "resource_type": "aws_ebs_volume",
                    "region": region,
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

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code not in ("UnauthorizedOperation", "AccessDenied"):
            raise

    total_carbon = sum(r["carbon"]["carbon_gco2e_month"] for r in resources)
    embodied_values = [
        r["carbon"]["embodied_gco2e_month"]
        for r in resources
        if r["carbon"]["embodied_gco2e_month"] is not None
    ]
    total_embodied = sum(embodied_values) if embodied_values else None
    total_energy = sum(r["carbon"]["energy_kwh_month"] for r in resources)
    total_cost   = sum(
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


# CCFT check 

def check_ccft_access(session: boto3.Session):
    """
    Try to call the AWS Customer Carbon Footprint Tool API.

    Required IAM permission: sustainability:GetCarbonFootprintSummary
    This call is read-only and free.
    """
    print("\n── Checking AWS CCFT Access ─────────────────────────────────────")

    try:
        # CCFT is only available in us-east-1
        client = session.client("sustainability", region_name="us-east-1")

        response = client.get_estimated_carbon_emissions(
            TimePeriod={"Start": "2024-01-01", "End": "2024-12-31"},
            Granularity="MONTHLY",
        )

        entries = response.get("EstimatedCarbonEmissions", [])
        if entries:
            print("  ✓ CCFT access confirmed! Sample data:")
            for entry in entries[:3]:  # Show first 3 months only
                print(f"    {entry.get('TimePeriod', {}).get('Start', 'N/A')}: "
                      f"{entry.get('EstimatedCarbonEmissions', 'N/A')} MTCO2e")
            print(f"\n  Full response has {len(entries)} monthly entries")
            print("  → These figures can be used to validate your estimates")
        else:
            print("  ✓ CCFT API accessible but no data returned")
            print("    (This is normal for new accounts or accounts with minimal usage)")

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "AccessDeniedException":
            print("  ✗ Access denied to CCFT API")
            print("    Missing IAM permission: sustainability:GetCarbonFootprintSummary")
            print("    Ask your AWS admin to grant this permission to your IAM role/user")
        elif error_code == "ValidationException":
            print("  ✗ Validation error - date range may be outside available data window")
        else:
            print(f"  ✗ Unexpected error: {error_code}")
            print(f"    {e}")
    except Exception as e:
        print(f"  ✗ Could not connect to CCFT: {e}")
        print("    Note: sustainability client requires boto3 >= 1.26.0")


# Main 

def main():
    parser = argparse.ArgumentParser(
        description="Scan real AWS infrastructure and estimate carbon footprint"
    )
    parser.add_argument("--region", default=None,
                        help="AWS region to scan (default: your configured default)")
    parser.add_argument("--profile", default=None,
                        help="AWS CLI profile to use")
    parser.add_argument("--all-regions", action="store_true",
                        help="Scan all supported regions (this will be slow)")
    parser.add_argument("--skip-ccft", action="store_true",
                        help="Skip the CCFT access check")
    args = parser.parse_args()

    # Set up AWS session 
    try:
        session = boto3.Session(profile_name=args.profile)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        account_id = identity["Account"]
        print(f"\nAWS Account: {account_id}")
        print(f"ARN:         {identity['Arn']}")
    except NoCredentialsError:
        print("Error: No AWS credentials found.")
        print("Configure with: aws configure  OR  set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY")
        sys.exit(1)
    except ClientError as e:
        print(f"Error authenticating with AWS: {e}")
        sys.exit(1)

    # Determine regions to scan 
    if args.all_regions:
        regions = SUPPORTED_REGIONS
    elif args.region:
        regions = [args.region]
    else:
        # Use the session's configured default region
        default_region = session.region_name or "eu-west-1"
        print(f"No region specified, scanning: {default_region}")
        regions = [default_region]

    # Scan each region 
    all_estimates = []

    for region in regions:
        print(f"\n── Scanning region: {region} ────────────────────────────────────")
        print("  EC2 Instances:")
        all_estimates.extend(scan_ec2_instances(region, session))
        print("  EBS Volumes:")
        all_estimates.extend(scan_ebs_volumes(region, session))
        print("  RDS Instances:")
        all_estimates.extend(scan_rds_instances(region, session))
        print("  Load Balancers (ALB/NLB):")
        all_estimates.extend(scan_elbs(region, session))

    # Print summary
    print_summary(all_estimates, title="Actual AWS Infrastructure Carbon Estimate")

    # Check CCFT access for validation
    if not args.skip_ccft:
        check_ccft_access(session)
    else:
        print("\n(CCFT check skipped)")


if __name__ == "__main__":
    main()
