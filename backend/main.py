"""
main.py — FastAPI application entry point for ResourceLens.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.database import init_db
from routes.upload import router as upload_router
from routes.analysis import router as analysis_router
from routes.review import router as review_router
from routes.verify import router as verify_router
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("resourcelens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ResourceLens starting — initialising database…")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("ResourceLens shutting down.")


app = FastAPI(
    title="ResourceLens API",
    description="Industrial energy and water loss investigation — Problem Statement 22",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(upload_router)
app.include_router(analysis_router)
app.include_router(review_router)
app.include_router(verify_router)


@app.get("/health")
def health():
    return {"status": "ok", "app": "ResourceLens", "version": "1.0.0"}


@app.get("/api/config/thresholds")
def get_thresholds():
    """Return current detection thresholds (for display in UI)."""
    return {
        "anomaly_threshold_pct": settings.ANOMALY_THRESHOLD_PCT,
        "anomaly_sigma": settings.ANOMALY_SIGMA,
        "baseline_weeks": settings.BASELINE_WEEKS,
        "water_unaccounted_threshold_kl": settings.WATER_UNACCOUNTED_THRESHOLD_KL,
        "energy_tariff_per_kwh": settings.ENERGY_TARIFF_PER_KWH,
        "water_tariff_per_kl": settings.WATER_TARIFF_PER_KL,
    }

