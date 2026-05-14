"""
api/routes/ccft.py

AWS Customer Carbon Footprint Tool (CCFT) endpoint.

GET /api/ccft/summary — returns monthly carbon emission data from the CCFT API
                        for use in the dashboard validation view.
"""

from __future__ import annotations

import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import APIRouter, HTTPException, Query

from api.config import settings

router = APIRouter(prefix="/ccft", tags=["ccft"])

# CCFT is only available in us-east-1
_CCFT_REGION = "us-east-1"


def _build_session() -> boto3.Session:
    """Return a boto3 Session configured from application settings."""
    kwargs: dict = {}
    if settings.aws_profile:
        kwargs["profile_name"] = settings.aws_profile
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.Session(**kwargs)


@router.get("/summary", summary="Fetch AWS Customer Carbon Footprint Tool summary")
async def ccft_summary(
    start_date: str = Query(
        default=None,
        description="Start of the reporting period (YYYY-MM-DD). "
                    "Defaults to the first day of 12 months ago.",
        examples=["2024-01-01"],
    ),
    end_date: str = Query(
        default=None,
        description="End of the reporting period (YYYY-MM-DD, exclusive). "
                    "Defaults to the first day of the current month.",
        examples=["2024-12-01"],
    ),
) -> dict:
    """
    Calls the AWS Sustainability API (``sustainability:GetCarbonFootprintSummary``)
    via the ``get_estimated_carbon_emissions`` boto3 method and returns monthly
    carbon emission entries for the configured AWS account.

    Requires the IAM permission ``sustainability:GetCarbonFootprintSummary``.

    Returns a JSON object with:

    * ``entries`` — list of monthly records, each containing ``start``,
      ``end``, and ``estimated_carbon_emissions_mtco2e``.
    * ``total_entries`` — total number of monthly records returned.
    """
    today = datetime.date.today()

    if start_date is None:
        # Default: exactly 12 calendar months before the start of the current month
        first_of_current_month = today.replace(day=1)
        start_date = first_of_current_month.replace(year=first_of_current_month.year - 1).isoformat()

    if end_date is None:
        # Default: start of the current month (CCFT data lags by ~3 months,
        # but requesting up to today avoids missing recent data)
        end_date = today.replace(day=1).isoformat()

    try:
        session = _build_session()
        client = session.client("sustainability", region_name=_CCFT_REGION)
        api_kwargs: dict = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": "MONTHLY",
            "GroupBy": ["SERVICE"],
        }
        # Optionally restrict to a single linked account to avoid summing across
        # all accounts in an AWS Organisation.
        if settings.aws_ccft_account_id:
            api_kwargs["Filter"] = {
                "Dimensions": {
                    "Key": "LINKED_ACCOUNT",
                    "Values": [settings.aws_ccft_account_id],
                }
            }
        response = client.get_estimated_carbon_emissions(**api_kwargs)
    except NoCredentialsError as exc:
        raise HTTPException(
            status_code=503,
            detail="AWS credentials not found. Configure credentials via environment "
                   "variables, an IAM role, or the AWS_PROFILE setting.",
        ) from exc
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "AccessDeniedException":
            raise HTTPException(
                status_code=403,
                detail="Access denied to the AWS CCFT API. "
                       "Ensure the IAM principal has the "
                       "sustainability:GetCarbonFootprintSummary permission.",
            ) from exc
        if error_code == "ValidationException":
            raise HTTPException(
                status_code=400,
                detail=f"AWS validation error: {exc.response['Error'].get('Message', error_code)}",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected AWS error ({error_code}): {exc.response['Error'].get('Message', '')}",
        ) from exc

    raw_entries = response.get("Results", [])

    # Group by month, collecting per-service values
    months: dict = {}
    for entry in raw_entries:
        start = str(entry.get("TimePeriod", {}).get("Start", ""))[:10]
        end   = str(entry.get("TimePeriod", {}).get("End",   ""))[:10]
        service = entry.get("DimensionsValues", {}).get("SERVICE", "Other")
        lbm = entry.get("EmissionsValues", {}).get("TOTAL_LBM_CARBON_EMISSIONS", {}).get("Value")
        mbm = entry.get("EmissionsValues", {}).get("TOTAL_MBM_CARBON_EMISSIONS", {}).get("Value")

        if start not in months:
            months[start] = {"start": start, "end": end, "services": {}}
        months[start]["services"][service] = {"lbm_mtco2e": lbm, "mbm_mtco2e": mbm}

    # Build final entries with per-service breakdown and totals
    entries = []
    for month in sorted(months.values(), key=lambda m: m["start"]):
        services = month["services"]
        total_lbm = round(sum(s["lbm_mtco2e"] or 0 for s in services.values()), 6)
        total_mbm = round(sum(s["mbm_mtco2e"] or 0 for s in services.values()), 6)
        ec2 = services.get("AmazonEC2", {})
        ec2_lbm = ec2.get("lbm_mtco2e")
        ec2_mbm = ec2.get("mbm_mtco2e")
        entries.append({
            "start": month["start"],
            "end":   month["end"],
            "total_lbm_mtco2e": total_lbm,
            "total_mbm_mtco2e": total_mbm,
            "ec2_lbm_mtco2e": round(ec2_lbm, 6) if ec2_lbm is not None else None,
            "ec2_mbm_mtco2e": round(ec2_mbm, 6) if ec2_mbm is not None else None,
            "services": services,
        })

    return {
        "period": {"start": start_date, "end": end_date},
        "total_entries": len(entries),
        "entries": entries,
    }
