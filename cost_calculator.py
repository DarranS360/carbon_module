"""
cost_calculator.py

AWS cost estimation using the AWS Pricing API.
Fetches real-time on-demand pricing for EC2, EBS, and RDS resources.

Pricing API is only available in us-east-1 and ap-south-1.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None

    class BotoCoreError(Exception):
        """Stub for botocore.BotoCoreError when botocore is not installed."""

    class ClientError(BotoCoreError):
        """Stub for botocore.ClientError when botocore is not installed."""

HOURS_PER_MONTH = 730

logger = logging.getLogger(__name__)


@dataclass
class CostEstimate:
    resource_type: str
    resource_id: str
    region: str
    instance_type: Optional[str]
    cost_usd_month: float
    pricing_details: dict

    def summary(self) -> str:
        return (
            f"  {self.resource_id} ({self.resource_type})\n"
            f"    Cost: ${self.cost_usd_month:.2f}/month"
        )


def get_ec2_price(instance_type: str, region: str, session=None) -> Optional[float]:
    """Fetch hourly on-demand price for an EC2 instance type in a region."""
    if not boto3:
        return None

    try:
        if session is None:
            session = boto3.Session()
        
        pricing = session.client("pricing", region_name="us-east-1")
        
        response = pricing.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": region_code_to_name(region)},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            ],
            MaxResults=1,
        )

        if not response.get("PriceList"):
            return None

        price_item = json.loads(response["PriceList"][0])
        on_demand = price_item["terms"]["OnDemand"]
        price_dimensions = list(on_demand.values())[0]["priceDimensions"]
        hourly_price = float(list(price_dimensions.values())[0]["pricePerUnit"]["USD"])
        
        return hourly_price

    except (BotoCoreError, ClientError, KeyError, IndexError, ValueError):
        return None


def get_ebs_price(volume_type: str, region: str, session=None) -> Optional[float]:
    """Fetch monthly price per GB for an EBS volume type in a region."""
    if not boto3:
        return None

    try:
        if session is None:
            session = boto3.Session()
        
        pricing = session.client("pricing", region_name="us-east-1")
        
        volume_api_type = {
            "gp2": "General Purpose",
            "gp3": "General Purpose",
            "io1": "Provisioned IOPS",
            "io2": "Provisioned IOPS",
            "st1": "Throughput Optimized HDD",
            "sc1": "Cold HDD",
            "standard": "Magnetic",
        }.get(volume_type, "General Purpose")

        response = pricing.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
                {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": volume_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": region_code_to_name(region)},
            ],
            MaxResults=1,
        )

        if not response.get("PriceList"):
            return None

        price_item = json.loads(response["PriceList"][0])
        on_demand = price_item["terms"]["OnDemand"]
        price_dimensions = list(on_demand.values())[0]["priceDimensions"]
        monthly_price_per_gb = float(list(price_dimensions.values())[0]["pricePerUnit"]["USD"])
        
        return monthly_price_per_gb

    except (BotoCoreError, ClientError, KeyError, IndexError, ValueError):
        return None


def _engine_to_api_name(engine: str) -> str:
    """Map a Terraform RDS engine string to the name used by the Pricing API."""
    mapping = {
        "mysql":              "MySQL",
        "postgres":           "PostgreSQL",
        "mariadb":            "MariaDB",
        "oracle-ee":          "Oracle",
        "oracle-se":          "Oracle",
        "oracle-se1":         "Oracle",
        "oracle-se2":         "Oracle",
        "sqlserver-ex":       "SQL Server",
        "sqlserver-web":      "SQL Server",
        "sqlserver-se":       "SQL Server",
        "sqlserver-ee":       "SQL Server",
        "aurora-mysql":       "Aurora MySQL",
        "aurora-postgresql":  "Aurora PostgreSQL",
    }
    return mapping.get(engine.lower(), "MySQL")


def get_rds_price(
    instance_class: str,
    region: str,
    engine: str = "mysql",
    multi_az: bool = False,
    session=None,
) -> Optional[float]:
    """Fetch hourly on-demand price for an RDS instance class in a region."""
    if not boto3:
        return None

    try:
        if session is None:
            session = boto3.Session()

        pricing = session.client("pricing", region_name="us-east-1")
        deployment_option = "Multi-AZ" if multi_az else "Single-AZ"
        database_engine   = _engine_to_api_name(engine)

        response = pricing.get_products(
            ServiceCode="AmazonRDS",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType",      "Value": instance_class},
                {"Type": "TERM_MATCH", "Field": "location",          "Value": region_code_to_name(region)},
                {"Type": "TERM_MATCH", "Field": "databaseEngine",    "Value": database_engine},
                {"Type": "TERM_MATCH", "Field": "deploymentOption",  "Value": deployment_option},
            ],
            MaxResults=1,
        )

        if not response.get("PriceList"):
            return None

        price_item      = json.loads(response["PriceList"][0])
        on_demand       = price_item["terms"]["OnDemand"]
        price_dimensions = list(on_demand.values())[0]["priceDimensions"]
        hourly_price    = float(list(price_dimensions.values())[0]["pricePerUnit"]["USD"])

        return hourly_price

    except (BotoCoreError, ClientError, KeyError, IndexError, ValueError):
        return None


def get_rds_storage_price(
    storage_type: str,
    region: str,
    multi_az: bool = False,
    session=None,
) -> Optional[float]:
    """Fetch monthly price per GB for an RDS storage type in a region."""
    if not boto3:
        return None

    try:
        if session is None:
            session = boto3.Session()

        pricing = session.client("pricing", region_name="us-east-1")
        deployment_option = "Multi-AZ" if multi_az else "Single-AZ"

        # Map storage type to the volume type string used in the Pricing API
        volume_type_map = {
            "gp2":      "General Purpose",
            "gp3":      "General Purpose",
            "io1":      "Provisioned IOPS",
            "io2":      "Provisioned IOPS",
            "magnetic": "Magnetic",
            "standard": "Magnetic",
        }
        api_volume_type = volume_type_map.get(storage_type, "General Purpose")

        response = pricing.get_products(
            ServiceCode="AmazonRDS",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "productFamily",    "Value": "Database Storage"},
                {"Type": "TERM_MATCH", "Field": "volumeType",       "Value": api_volume_type},
                {"Type": "TERM_MATCH", "Field": "location",         "Value": region_code_to_name(region)},
                {"Type": "TERM_MATCH", "Field": "deploymentOption", "Value": deployment_option},
            ],
            MaxResults=1,
        )

        if not response.get("PriceList"):
            return None

        price_item       = json.loads(response["PriceList"][0])
        on_demand        = price_item["terms"]["OnDemand"]
        price_dimensions = list(on_demand.values())[0]["priceDimensions"]
        price_per_gb     = float(list(price_dimensions.values())[0]["pricePerUnit"]["USD"])

        return price_per_gb

    except (BotoCoreError, ClientError, KeyError, IndexError, ValueError):
        return None


def region_code_to_name(region_code: str) -> str:
    """Convert AWS region code to the location name used by Pricing API."""
    mapping = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-1": "US West (N. California)",
        "us-west-2": "US West (Oregon)",
        "ca-central-1": "Canada (Central)",
        "ca-west-1": "Canada West (Calgary)",
        "eu-west-1": "EU (Ireland)",
        "eu-west-2": "EU (London)",
        "eu-west-3": "EU (Paris)",
        "eu-central-1": "EU (Frankfurt)",
        "eu-central-2": "EU (Zurich)",
        "eu-north-1": "EU (Stockholm)",
        "eu-south-1": "EU (Milan)",
        "eu-south-2": "EU (Spain)",
        "ap-east-1": "Asia Pacific (Hong Kong)",
        "ap-east-2": "Asia Pacific (Taipei)",
        "ap-southeast-1": "Asia Pacific (Singapore)",
        "ap-southeast-2": "Asia Pacific (Sydney)",
        "ap-southeast-3": "Asia Pacific (Jakarta)",
        "ap-southeast-4": "Asia Pacific (Melbourne)",
        "ap-southeast-5": "Asia Pacific (Malaysia)",
        "ap-southeast-6": "Asia Pacific (New Zealand)",
        "ap-southeast-7": "Asia Pacific (Thailand)",
        "ap-northeast-1": "Asia Pacific (Tokyo)",
        "ap-northeast-2": "Asia Pacific (Seoul)",
        "ap-northeast-3": "Asia Pacific (Osaka)",
        "ap-south-1": "Asia Pacific (Mumbai)",
        "ap-south-2": "Asia Pacific (Hyderabad)",
        "sa-east-1": "South America (Sao Paulo)",
        "il-central-1": "Israel (Tel Aviv)",
        "me-south-1": "Middle East (Bahrain)",
        "me-central-1": "Middle East (UAE)",
        "mx-central-1": "Mexico (Central)",
        "af-south-1": "Africa (Cape Town)",
    }
    return mapping.get(region_code, region_code)


def estimate_ec2_cost(
    instance_type: str,
    region: str,
    resource_id: str = "unknown",
    hours: float = HOURS_PER_MONTH,
    session=None,
) -> Optional[CostEstimate]:
    """Estimate monthly cost for an EC2 instance."""
    
    hourly_price = get_ec2_price(instance_type, region, session)
    
    if hourly_price is None:
        logger.warning("Could not fetch pricing for %s in %s", instance_type, region)
        return None

    monthly_cost = hourly_price * hours

    return CostEstimate(
        resource_type="aws_instance",
        resource_id=resource_id,
        region=region,
        instance_type=instance_type,
        cost_usd_month=monthly_cost,
        pricing_details={
            "hourly_price_usd": hourly_price,
            "hours": hours,
        },
    )


def estimate_ebs_cost(
    size_gb: float,
    volume_type: str,
    region: str,
    resource_id: str = "unknown",
    session=None,
) -> Optional[CostEstimate]:
    """Estimate monthly cost for an EBS volume."""
    
    price_per_gb = get_ebs_price(volume_type, region, session)
    
    if price_per_gb is None:
        logger.warning("Could not fetch pricing for EBS %s in %s", volume_type, region)
        return None

    monthly_cost = price_per_gb * size_gb

    return CostEstimate(
        resource_type="aws_ebs_volume",
        resource_id=resource_id,
        region=region,
        instance_type=f"EBS {volume_type} {size_gb}GB",
        cost_usd_month=monthly_cost,
        pricing_details={
            "price_per_gb_month_usd": price_per_gb,
            "size_gb": size_gb,
        },
    )


def estimate_rds_cost(
    instance_class: str,
    region: str,
    storage_gb: float = 0,
    storage_type: str = "gp2",
    engine: str = "mysql",
    multi_az: bool = False,
    resource_id: str = "unknown",
    hours: float = HOURS_PER_MONTH,
    session=None,
) -> Optional[CostEstimate]:
    """Estimate monthly cost for an RDS instance (compute + storage)."""

    hourly_price  = get_rds_price(instance_class, region, engine, multi_az, session)
    price_per_gb  = get_rds_storage_price(storage_type, region, multi_az, session)

    if hourly_price is None:
        logger.warning("Could not fetch RDS pricing for %s (%s) in %s", instance_class, engine, region)
        return None

    compute_cost = hourly_price * hours
    storage_cost = (price_per_gb * storage_gb) if price_per_gb is not None else 0.0
    monthly_cost = compute_cost + storage_cost

    deployment = "Multi-AZ" if multi_az else "Single-AZ"

    return CostEstimate(
        resource_type="aws_db_instance",
        resource_id=resource_id,
        region=region,
        instance_type=instance_class,
        cost_usd_month=monthly_cost,
        pricing_details={
            "engine":             engine,
            "deployment_option":  deployment,
            "hourly_price_usd":   hourly_price,
            "hours":              hours,
            "compute_cost_usd":   round(compute_cost, 4),
            "storage_gb":         storage_gb,
            "storage_type":       storage_type,
            "price_per_gb_month_usd": price_per_gb,
            "storage_cost_usd":   round(storage_cost, 4),
        },
    )


def get_elb_price(lb_type: str, region: str, session=None) -> Optional[float]:
    """Fetch hourly on-demand price for an Elastic Load Balancer type in a region."""
    if not boto3:
        return None

    try:
        if session is None:
            session = boto3.Session()

        pricing = session.client("pricing", region_name="us-east-1")

        # ALB and NLB are in the "AmazonEC2" service with productFamily "Load Balancer"
        # CLB (classic) is in "ElasticLoadBalancing"
        normalised = lb_type.lower()
        if normalised == "classic":
            service_code = "ElasticLoadBalancing"
            filters = [
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Load Balancer"},
                {"Type": "TERM_MATCH", "Field": "location", "Value": region_code_to_name(region)},
            ]
        else:
            # ALB, NLB, GWLB — ELBv2, reported under AmazonEC2 pricing
            group_map = {
                "application": "ELB:Balancer:ALB",
                "network":     "ELB:Balancer:NLB",
                "gateway":     "ELB:Balancer:GWB",
            }
            group = group_map.get(normalised, "ELB:Balancer:ALB")
            service_code = "AmazonEC2"
            filters = [
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Load Balancer"},
                {"Type": "TERM_MATCH", "Field": "group",         "Value": group},
                {"Type": "TERM_MATCH", "Field": "location",      "Value": region_code_to_name(region)},
            ]

        response = pricing.get_products(
            ServiceCode=service_code,
            Filters=filters,
            MaxResults=1,
        )

        if not response.get("PriceList"):
            return None

        price_item = json.loads(response["PriceList"][0])
        on_demand = price_item["terms"]["OnDemand"]
        price_dimensions = list(on_demand.values())[0]["priceDimensions"]
        hourly_price = float(list(price_dimensions.values())[0]["pricePerUnit"]["USD"])

        return hourly_price

    except (BotoCoreError, ClientError, KeyError, IndexError, ValueError):
        return None


def estimate_elb_cost(
    lb_type: str,
    region: str,
    resource_id: str = "unknown",
    hours: float = HOURS_PER_MONTH,
    session=None,
) -> Optional[CostEstimate]:
    """Estimate monthly cost for an Elastic Load Balancer (base hourly charge only)."""

    hourly_price = get_elb_price(lb_type, region, session)

    if hourly_price is None:
        logger.warning("Could not fetch pricing for ELB %s in %s", lb_type, region)
        return None

    monthly_cost = hourly_price * hours

    return CostEstimate(
        resource_type="aws_lb",
        resource_id=resource_id,
        region=region,
        instance_type=f"ELB ({lb_type})",
        cost_usd_month=monthly_cost,
        pricing_details={
            "hourly_price_usd": hourly_price,
            "hours": hours,
            "note": "Base hourly charge only; LCU charges not included.",
        },
    )


def print_cost_summary(estimates: list[CostEstimate], title: str = "Cost Estimate Summary"):
    """Print a readable summary of all cost estimates."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

    if not estimates:
        print("  No cost estimates produced.")
        return

    total_cost = sum(e.cost_usd_month for e in estimates)

    for e in estimates:
        print(e.summary())

    print(f"{'─'*60}")
    print(f"  TOTAL Cost: ${total_cost:.2f}/month (${total_cost * 12:.2f}/year)")
    print(f"{'='*60}\n")
