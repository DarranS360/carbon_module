"""
api/routes/billing.py

AWS Cost Explorer billing endpoint.

GET /api/billing/summary — returns monthly cost breakdown by service.
"""

from __future__ import annotations

import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import APIRouter, HTTPException, Query

from api.config import settings

router = APIRouter(prefix="/billing", tags=["billing"])

# Services to break out individually — everything else is grouped as "Other"
TOP_SERVICES = {
    "Amazon Elastic Compute Cloud - Compute": "EC2 Compute",
    "EC2 - Other":                            "EC2 Other",
    "Amazon Elastic Container Service for Kubernetes": "EKS",
    "Amazon Virtual Private Cloud":           "VPC",
    "Amazon Elastic Load Balancing":          "Load Balancing",
    "AmazonCloudWatch":                       "CloudWatch",
    "Amazon DynamoDB":                        "DynamoDB",
}


def _build_session() -> boto3.Session:
    kwargs: dict = {}
    if settings.aws_profile:
        kwargs["profile_name"] = settings.aws_profile
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.Session(**kwargs)


@router.get("/summary", summary="Fetch monthly AWS cost breakdown from Cost Explorer")
async def billing_summary(
    start_date: str = Query(
        default=None,
        description="Start of the reporting period (YYYY-MM-DD). Defaults to 12 months ago.",
    ),
    end_date: str = Query(
        default=None,
        description="End of the reporting period (YYYY-MM-DD). Defaults to start of current month.",
    ),
) -> dict:
    """
    Calls the AWS Cost Explorer API to return monthly unblended costs grouped
    by service. Services below the top tracked list are grouped as 'Other'.
    Tax is excluded from totals.
    """
    today = datetime.date.today()

    if start_date is None:
        start_date = today.replace(day=1, year=today.year - 1).isoformat()
    if end_date is None:
        end_date = today.replace(day=1).isoformat()

    try:
        session = _build_session()
        ce = session.client("ce", region_name="us-east-1")
        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
    except NoCredentialsError as exc:
        raise HTTPException(status_code=503, detail="AWS credentials not found.") from exc
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "AccessDeniedException":
            raise HTTPException(
                status_code=403,
                detail="Access denied to Cost Explorer. Ensure the IAM principal has ce:GetCostAndUsage permission.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected AWS error ({error_code}): {exc.response['Error'].get('Message', '')}",
        ) from exc

    entries = []
    for result in response["ResultsByTime"]:
        month_start = result["TimePeriod"]["Start"][:10]
        month_end   = result["TimePeriod"]["End"][:10]

        services: dict[str, float] = {}
        other = 0.0
        total = 0.0

        for group in result["Groups"]:
            service_name = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])

            # Exclude tax from totals and breakdown
            if service_name == "Tax":
                continue

            total += amount

            if service_name in TOP_SERVICES:
                label = TOP_SERVICES[service_name]
                services[label] = round(amount, 2)
            else:
                other += amount

        if other > 0:
            services["Other"] = round(other, 2)

        entries.append({
            "start":    month_start,
            "end":      month_end,
            "total":    round(total, 2),
            "services": services,
        })

    return {
        "period":       {"start": start_date, "end": end_date},
        "total_entries": len(entries),
        "entries":      entries,
    }
