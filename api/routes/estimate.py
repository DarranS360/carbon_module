"""
api/routes/estimate.py

Carbon + cost estimation endpoints.

POST /api/estimate/plan   — accepts a Terraform plan JSON body and returns
                            per-resource carbon & cost estimates.
GET  /api/estimate/live   — triggers a live AWS scan for a given region and
                            returns estimates for resources that are running.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so that terraform_estimate and its
# dependencies (calculator, cost_calculator) can be imported.
_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import terraform_estimate  # noqa: E402
import aws_actual          # noqa: E402

from fastapi import APIRouter, HTTPException
from api.config import settings

router = APIRouter(prefix="/estimate", tags=["estimate"])


def _build_session():
    """Return a boto3 Session configured from application settings."""
    import boto3
    kwargs: dict = {}
    if settings.aws_profile:
        kwargs["profile_name"] = settings.aws_profile
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.Session(**kwargs)


@router.post("/plan", summary="Estimate carbon & cost from a Terraform plan")
async def estimate_plan(plan: dict) -> dict:
    """
    Accepts a Terraform plan JSON object and returns carbon and cost estimates
    for each resource that would be created.

    Expected body: the JSON output of ``terraform show -json tfplan``.
    """
    return terraform_estimate.estimate_from_plan_dict(plan)


@router.get("/live", summary="Estimate carbon & cost from live AWS infrastructure")
async def estimate_live(
    region: str = "eu-west-1",
    cpu_utilisation: float = 0.50,
) -> dict:
    """
    Scans running AWS infrastructure in the specified region and returns
    carbon and cost estimates for discovered resources.

    ``cpu_utilisation`` (0–1) controls the assumed CPU load for EC2 instances;
    defaults to the CCF standard of 0.50 (50%). Use a lower value (e.g. 0.12)
    if you have CloudWatch data showing your actual average utilisation.

    Requires valid AWS credentials to be available in the environment
    (e.g. via ``aws configure``, environment variables, or an IAM role).
    """
    try:
        session = _build_session()
        # Validate that credentials are available before scanning.
        sts = session.client("sts")
        sts.get_caller_identity()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="AWS credentials are not available or are invalid. "
                   "Configure credentials via the AWS CLI, environment variables, or an IAM role.",
        )

    return aws_actual.estimate_from_live(
        region=region,
        session=session,
        cpu_utilisation=max(0.0, min(1.0, cpu_utilisation)),
    )
