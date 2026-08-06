"""

Project : AEGIS
System : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File : main.py
Version : 3.0.0 - Queue/Worker-Pool Trading Architecture

Purpose : FastAPI application entry point.

"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_allowed_origins, settings
from app.core.logging import configure_logging
from app.core.startup import on_startup, on_shutdown

# Routers
from app.api.upload_router import router as upload_router
from app.api.preprocessing_router import router as preprocessing_router
from app.api.chart_detection_router import router as chart_detection_router
from app.api.router import router as base_router
from app.api.trading_router import router as trading_router
from app.api.brain_router import router as brain_router
from app.api.subscription_router import router as subscription_router
from app.api.download_router import router as download_router
from app.api.device_router import router as device_router
from app.api.admin_router import router as admin_router
from app.api.portal_router import router as portal_router

logger = configure_logging(__name__)

app = FastAPI(
    title="AEGIS API",
    description="Autonomous Enterprise Global Intelligence System",
    version="3.0.0",
    debug=settings.DEBUG,  # was previously defined in config but never actually wired up
)

# CORS - explicit origin allowlist required. "*" + credentials is both
# rejected by browsers and unsafe, so it's deliberately not supported here.
origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    await on_startup(app)
    logger.info("AEGIS API v3.0.0 Started")


@app.on_event("shutdown")
async def shutdown_event():
    await on_shutdown(app)
    logger.info("AEGIS API Shut Down")

# ==========================================================
# INCLUDE ALL ROUTERS
# ==========================================================

app.include_router(base_router)
app.include_router(upload_router)
app.include_router(preprocessing_router)
app.include_router(chart_detection_router)
app.include_router(trading_router)
app.include_router(brain_router)
app.include_router(subscription_router)
app.include_router(download_router)
app.include_router(device_router)
app.include_router(admin_router)
app.include_router(portal_router)

# /metrics - HTTP request counts/latencies auto-instrumented, plus custom
# business gauges from app.core.metrics (populated by a background loop
# started in on_startup). Put behind your reverse proxy / firewall in
# production - this isn't behind verify_api_key, matching how Prometheus
# scraping conventionally works (network-level access control instead).
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Static frontends - served directly by this app so there's nothing
# extra to deploy. Mounted last so they don't shadow any API route.
_frontend_root = Path(__file__).resolve().parents[2]  # repo root
admin_dir = _frontend_root / "admin_dashboard"
portal_dir = _frontend_root / "client_portal"
if admin_dir.exists():
    app.mount("/admin", StaticFiles(directory=str(admin_dir), html=True), name="admin_dashboard")
if portal_dir.exists():
    app.mount("/portal", StaticFiles(directory=str(portal_dir), html=True), name="client_portal")


@app.get("/")
async def root():
    return {
        "service": "AEGIS API",
        "version": "3.0.0",
        "status": "online",
        "modules": ["upload", "preprocessing", "chart_detection", "trading", "brain", "subscriptions", "download", "devices", "admin", "portal"],
    }
