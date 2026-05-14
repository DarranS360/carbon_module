"""
api/main.py

FastAPI application entry point.

Responsibilities:
  - Create the FastAPI app instance
  - Register CORS middleware (origins read from config)
  - Mount /api route prefix and include all routers
  - Expose a health-check endpoint at GET /api/health
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import calculator
from api.config import settings
from api.dependencies import verify_api_key
from api.routes import estimate, ccft, billing
from embodied_data import ensure_embodied_data_current


logger = logging.getLogger("uvicorn.error")

# App 

app = FastAPI(
    title="Carbon Cost Module API",
    description=(
        "Estimates carbon footprint and AWS cost for infrastructure resources "
        "defined in a Terraform plan or running live in AWS."
    ),
    version="0.1.0",
    # Disable /docs and /redoc in production
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

# CORS

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers

app.include_router(estimate.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(ccft.router,     prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(billing.router,  prefix="/api", dependencies=[Depends(verify_api_key)])


@app.on_event("startup")
async def refresh_embodied_lookup() -> None:
    result = ensure_embodied_data_current(
        max_age_days=settings.embodied_refresh_max_age_days,
        enabled=settings.embodied_refresh_enabled,
        logger=logger,
    )
    factor_count = calculator.reload_embodied_data()
    logger.info(
        "Embodied carbon lookup ready: %s factors loaded (refreshed=%s, reason=%s)",
        factor_count,
        result.get("refreshed", False),
        result.get("reason", "refreshed"),
    )

# Health check

@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    """Returns a simple liveness response."""
    return {"status": "ok", "env": settings.app_env}
