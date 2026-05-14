"""
tests/test_api.py

Integration tests for the FastAPI endpoints.

Uses FastAPI's TestClient to call endpoints without a real server.
boto3 calls are mocked with unittest.mock.patch so no AWS credentials
are needed.  The tests assert response shape and routing correctness,
not specific AWS values.
"""

import os
import sys
import json
from unittest.mock import MagicMock, patch

import pytest

# Ensure the repo root is on sys.path before importing app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Disable API key auth and any external calls during tests
os.environ.setdefault("API_KEY", "")
os.environ.setdefault("APP_ENV", "test")

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


# ── Minimal valid Terraform plan fixture ──────────────────────────────────────

MINIMAL_PLAN = {
    "format_version": "1.0",
    "configuration": {
        "provider_config": {
            "aws": {
                "expressions": {
                    "region": {"constant_value": "eu-west-1"}
                }
            }
        }
    },
    "resource_changes": [
        {
            "address": "aws_instance.web",
            "type": "aws_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "instance_type": "t3.medium",
                    "availability_zone": "eu-west-1a",
                },
            },
        },
        {
            "address": "aws_ebs_volume.data",
            "type": "aws_ebs_volume",
            "change": {
                "actions": ["create"],
                "after": {
                    "size": 100,
                    "type": "gp2",
                    "availability_zone": "eu-west-1a",
                },
            },
        },
        {
            "address": "aws_db_instance.db",
            "type": "aws_db_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "instance_class": "db.t3.medium",
                    "availability_zone": "eu-west-1a",
                    "allocated_storage": 20,
                    "storage_type": "gp2",
                    "engine": "mysql",
                    "multi_az": False,
                },
            },
        },
    ],
}


# ── POST /api/estimate/plan ───────────────────────────────────────────────────

class TestEstimatePlan:
    """Integration tests for POST /api/estimate/plan."""

    def test_valid_plan_returns_200(self):
        """A well-formed Terraform plan body should return HTTP 200."""
        response = client.post("/api/estimate/plan", json=MINIMAL_PLAN)
        assert response.status_code == 200

    def test_response_contains_required_keys(self):
        """Response must contain 'resources', 'totals', and 'skipped' keys."""
        response = client.post("/api/estimate/plan", json=MINIMAL_PLAN)
        body = response.json()
        assert "resources" in body
        assert "totals" in body
        assert "skipped" in body

    def test_resources_list_is_non_empty(self):
        """The plan contains three supported resources; all should be estimated."""
        response = client.post("/api/estimate/plan", json=MINIMAL_PLAN)
        body = response.json()
        assert len(body["resources"]) == 3

    def test_totals_contain_carbon_and_energy(self):
        """The totals block must include carbon and energy figures."""
        response = client.post("/api/estimate/plan", json=MINIMAL_PLAN)
        totals = response.json()["totals"]
        assert "carbon_gco2e_month" in totals
        assert "energy_kwh_month" in totals
        assert totals["carbon_gco2e_month"] > 0
        assert totals["energy_kwh_month"] > 0

    def test_each_resource_has_carbon_block(self):
        """Each resource entry must include a 'carbon' sub-dict."""
        response = client.post("/api/estimate/plan", json=MINIMAL_PLAN)
        for resource in response.json()["resources"]:
            assert "carbon" in resource
            assert resource["carbon"]["carbon_gco2e_month"] > 0

    def test_unsupported_resource_type_goes_to_skipped(self):
        """Resources with unsupported types must appear in 'skipped'."""
        plan_with_unknown = {
            **MINIMAL_PLAN,
            "resource_changes": [
                {
                    "address": "aws_lambda_function.fn",
                    "type": "aws_lambda_function",
                    "change": {
                        "actions": ["create"],
                        "after": {"function_name": "my-fn"},
                    },
                }
            ],
        }
        response = client.post("/api/estimate/plan", json=plan_with_unknown)
        body = response.json()
        assert "aws_lambda_function.fn" in body["skipped"]
        assert len(body["resources"]) == 0

    def test_empty_plan_returns_empty_results(self):
        """A plan with no resource_changes should return empty resources."""
        empty_plan = {**MINIMAL_PLAN, "resource_changes": []}
        response = client.post("/api/estimate/plan", json=empty_plan)
        body = response.json()
        assert body["resources"] == []
        assert body["skipped"] == []


# ── GET /api/estimate/live ────────────────────────────────────────────────────

class TestEstimateLive:
    """Integration tests for GET /api/estimate/live (boto3 mocked)."""

    def _make_mock_session(self):
        """Return a mock boto3 Session that simulates running EC2/RDS/EBS."""
        session = MagicMock()

        # STS — credential check passes
        sts = MagicMock()
        sts.get_caller_identity.return_value = {"Account": "123456789012"}

        # EC2 — one running t3.medium instance, no EBS volumes (separate paginator)
        ec2 = MagicMock()
        ec2_paginator = MagicMock()
        ec2_paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-0abc123",
                                "InstanceType": "t3.medium",
                                "Tags": [{"Key": "Name", "Value": "web-server"}],
                            }
                        ]
                    }
                ]
            }
        ]
        ebs_paginator = MagicMock()
        ebs_paginator.paginate.return_value = [{"Volumes": []}]

        def ec2_get_paginator(name):
            if name == "describe_instances":
                return ec2_paginator
            return ebs_paginator

        ec2.get_paginator.side_effect = ec2_get_paginator

        # RDS — no instances
        rds = MagicMock()
        rds_paginator = MagicMock()
        rds_paginator.paginate.return_value = [{"DBInstances": []}]
        rds.get_paginator.return_value = rds_paginator

        def session_client(service, **kwargs):
            if service == "sts":
                return sts
            if service == "ec2":
                return ec2
            if service == "rds":
                return rds
            return MagicMock()

        session.client.side_effect = session_client
        return session

    @patch("api.routes.estimate._build_session")
    def test_live_returns_200(self, mock_build):
        """GET /api/estimate/live with valid mocked credentials returns HTTP 200."""
        mock_build.return_value = self._make_mock_session()
        response = client.get("/api/estimate/live?region=eu-west-1")
        assert response.status_code == 200

    @patch("api.routes.estimate._build_session")
    def test_live_response_shape(self, mock_build):
        """Response must contain 'resources', 'totals', and 'skipped'."""
        mock_build.return_value = self._make_mock_session()
        response = client.get("/api/estimate/live?region=eu-west-1")
        body = response.json()
        assert "resources" in body
        assert "totals" in body
        assert "skipped" in body

    @patch("api.routes.estimate._build_session")
    def test_live_includes_ec2_resource(self, mock_build):
        """A running EC2 instance should appear in the resources list."""
        mock_build.return_value = self._make_mock_session()
        response = client.get("/api/estimate/live?region=eu-west-1")
        body = response.json()
        assert len(body["resources"]) >= 1
        types = [r["resource_type"] for r in body["resources"]]
        assert "aws_instance" in types

    @patch("api.routes.estimate._build_session")
    def test_live_invalid_credentials_returns_503(self, mock_build):
        """When AWS credentials are unavailable the endpoint should return 503."""
        session = MagicMock()
        session.client.return_value.get_caller_identity.side_effect = Exception("no creds")
        mock_build.return_value = session
        response = client.get("/api/estimate/live?region=eu-west-1")
        assert response.status_code == 503


# ── GET /api/ccft/summary ─────────────────────────────────────────────────────

class TestCCFTSummary:
    """Integration tests for GET /api/ccft/summary (boto3 mocked)."""

    _CCFT_RESPONSE = {
        "Results": [
            {
                "TimePeriod": {"Start": "2024-01-01", "End": "2024-02-01"},
                "DimensionsValues": {"SERVICE": "AmazonEC2"},
                "EmissionsValues": {
                    "TOTAL_LBM_CARBON_EMISSIONS": {"Value": 0.0012},
                    "TOTAL_MBM_CARBON_EMISSIONS": {"Value": 0.0003},
                },
            },
            {
                "TimePeriod": {"Start": "2024-01-01", "End": "2024-02-01"},
                "DimensionsValues": {"SERVICE": "AmazonS3"},
                "EmissionsValues": {
                    "TOTAL_LBM_CARBON_EMISSIONS": {"Value": 0.0005},
                    "TOTAL_MBM_CARBON_EMISSIONS": {"Value": 0.0002},
                },
            },
        ]
    }

    @patch("api.routes.ccft._build_session")
    def test_ccft_returns_200(self, mock_build):
        """GET /api/ccft/summary with valid mock returns HTTP 200."""
        session = MagicMock()
        client_mock = MagicMock()
        client_mock.get_estimated_carbon_emissions.return_value = self._CCFT_RESPONSE
        session.client.return_value = client_mock
        mock_build.return_value = session

        response = client.get("/api/ccft/summary")
        assert response.status_code == 200

    @patch("api.routes.ccft._build_session")
    def test_ccft_response_shape(self, mock_build):
        """Response must contain 'period', 'total_entries', and 'entries'."""
        session = MagicMock()
        client_mock = MagicMock()
        client_mock.get_estimated_carbon_emissions.return_value = self._CCFT_RESPONSE
        session.client.return_value = client_mock
        mock_build.return_value = session

        body = client.get("/api/ccft/summary").json()
        assert "period" in body
        assert "total_entries" in body
        assert "entries" in body

    @patch("api.routes.ccft._build_session")
    def test_ccft_entries_contain_emission_totals(self, mock_build):
        """Each entry must include total and EC2-only lbm/mbm figures."""
        session = MagicMock()
        client_mock = MagicMock()
        client_mock.get_estimated_carbon_emissions.return_value = self._CCFT_RESPONSE
        session.client.return_value = client_mock
        mock_build.return_value = session

        body = client.get("/api/ccft/summary").json()
        assert len(body["entries"]) == 1
        entry = body["entries"][0]
        assert "total_lbm_mtco2e" in entry
        assert "total_mbm_mtco2e" in entry
        assert "ec2_lbm_mtco2e" in entry
        assert "ec2_mbm_mtco2e" in entry
        # totals include all services (EC2 + S3)
        assert entry["total_lbm_mtco2e"] == pytest.approx(0.0017)
        assert entry["total_mbm_mtco2e"] == pytest.approx(0.0005)
        # EC2-only fields
        assert entry["ec2_lbm_mtco2e"] == pytest.approx(0.0012)
        assert entry["ec2_mbm_mtco2e"] == pytest.approx(0.0003)

    @patch("api.routes.ccft._build_session")
    def test_ccft_ec2_only_null_when_no_ec2_service(self, mock_build):
        """ec2_lbm_mtco2e and ec2_mbm_mtco2e are None when AmazonEC2 is absent."""
        session = MagicMock()
        client_mock = MagicMock()
        client_mock.get_estimated_carbon_emissions.return_value = {
            "Results": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-02-01"},
                    "DimensionsValues": {"SERVICE": "AmazonS3"},
                    "EmissionsValues": {
                        "TOTAL_LBM_CARBON_EMISSIONS": {"Value": 0.0005},
                        "TOTAL_MBM_CARBON_EMISSIONS": {"Value": 0.0002},
                    },
                }
            ]
        }
        session.client.return_value = client_mock
        mock_build.return_value = session

        body = client.get("/api/ccft/summary").json()
        entry = body["entries"][0]
        assert entry["ec2_lbm_mtco2e"] is None
        assert entry["ec2_mbm_mtco2e"] is None

    @patch("api.routes.ccft.settings")
    @patch("api.routes.ccft._build_session")
    def test_ccft_account_filter_applied(self, mock_build, mock_settings):
        """When aws_ccft_account_id is set, a LINKED_ACCOUNT filter is sent."""
        mock_settings.aws_ccft_account_id = "123456789012"

        session = MagicMock()
        client_mock = MagicMock()
        client_mock.get_estimated_carbon_emissions.return_value = {"Results": []}
        session.client.return_value = client_mock
        mock_build.return_value = session

        client.get("/api/ccft/summary")

        call_kwargs = client_mock.get_estimated_carbon_emissions.call_args[1]
        assert "Filter" in call_kwargs
        assert call_kwargs["Filter"]["Dimensions"]["Key"] == "LINKED_ACCOUNT"
        assert "123456789012" in call_kwargs["Filter"]["Dimensions"]["Values"]

    @patch("api.routes.ccft.settings")
    @patch("api.routes.ccft._build_session")
    def test_ccft_no_account_filter_when_unset(self, mock_build, mock_settings):
        """When aws_ccft_account_id is empty, no Filter is sent."""
        mock_settings.aws_ccft_account_id = ""

        session = MagicMock()
        client_mock = MagicMock()
        client_mock.get_estimated_carbon_emissions.return_value = {"Results": []}
        session.client.return_value = client_mock
        mock_build.return_value = session

        client.get("/api/ccft/summary")

        call_kwargs = client_mock.get_estimated_carbon_emissions.call_args[1]
        assert "Filter" not in call_kwargs

    @patch("api.routes.ccft._build_session")
    def test_ccft_no_credentials_returns_503(self, mock_build):
        """Missing AWS credentials must return 503."""
        from botocore.exceptions import NoCredentialsError
        session = MagicMock()
        session.client.side_effect = NoCredentialsError()
        mock_build.return_value = session

        response = client.get("/api/ccft/summary")
        assert response.status_code == 503


# ── GET /api/billing/summary ──────────────────────────────────────────────────

class TestBillingSummary:
    """Integration tests for GET /api/billing/summary (boto3 mocked)."""

    _CE_RESPONSE = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2024-01-01", "End": "2024-02-01"},
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {"UnblendedCost": {"Amount": "123.45", "Unit": "USD"}},
                    },
                    {
                        "Keys": ["Tax"],
                        "Metrics": {"UnblendedCost": {"Amount": "10.00", "Unit": "USD"}},
                    },
                ],
                "Total": {},
                "Estimated": False,
            }
        ]
    }

    @patch("api.routes.billing._build_session")
    def test_billing_returns_200(self, mock_build):
        """GET /api/billing/summary with valid mock returns HTTP 200."""
        session = MagicMock()
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = self._CE_RESPONSE
        session.client.return_value = ce
        mock_build.return_value = session

        response = client.get("/api/billing/summary")
        assert response.status_code == 200

    @patch("api.routes.billing._build_session")
    def test_billing_response_shape(self, mock_build):
        """Response must contain 'period', 'total_entries', and 'entries'."""
        session = MagicMock()
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = self._CE_RESPONSE
        session.client.return_value = ce
        mock_build.return_value = session

        body = client.get("/api/billing/summary").json()
        assert "period" in body
        assert "total_entries" in body
        assert "entries" in body

    @patch("api.routes.billing._build_session")
    def test_billing_tax_excluded_from_total(self, mock_build):
        """Tax line items must be excluded from the monthly total."""
        session = MagicMock()
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = self._CE_RESPONSE
        session.client.return_value = ce
        mock_build.return_value = session

        body = client.get("/api/billing/summary").json()
        entry = body["entries"][0]
        # Total should be 123.45, not 123.45 + 10.00
        assert entry["total"] == pytest.approx(123.45, abs=0.01)

    @patch("api.routes.billing._build_session")
    def test_billing_known_service_labelled_correctly(self, mock_build):
        """A known service should appear in the services breakdown under its label."""
        session = MagicMock()
        ce = MagicMock()
        ce.get_cost_and_usage.return_value = self._CE_RESPONSE
        session.client.return_value = ce
        mock_build.return_value = session

        body = client.get("/api/billing/summary").json()
        services = body["entries"][0]["services"]
        assert "EC2 Compute" in services
        assert services["EC2 Compute"] == pytest.approx(123.45, abs=0.01)

    @patch("api.routes.billing._build_session")
    def test_billing_no_credentials_returns_503(self, mock_build):
        """Missing AWS credentials must return 503."""
        from botocore.exceptions import NoCredentialsError
        session = MagicMock()
        session.client.side_effect = NoCredentialsError()
        mock_build.return_value = session

        response = client.get("/api/billing/summary")
        assert response.status_code == 503
