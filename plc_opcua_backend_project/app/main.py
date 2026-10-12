import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from app.plc_client import test_plc_connection  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started without PostgreSQL.")
    yield
    logger.info("Application shutting down.")

app = FastAPI(
    title="PLC Monitoring Backend - OPC UA Test Mode",
    version="1.0.0",
    description="Temporary PostgreSQL-free application for testing OPC UA connectivity.",
    lifespan=lifespan,
)

@app.get("/")
async def home():
    return {
        "application": "PLC Monitoring Backend",
        "status": "running",
        "database_enabled": False,
        "opcua_endpoint_configured": bool(
            os.getenv("OPCUA_ENDPOINT", "").strip()
        ),
        "opcua_node_ids_configured": bool(
            os.getenv("OPCUA_NODE_IDS", "").strip()
        ),
        "docs": "/docs",
    }

@app.get("/plc/test")
async def plc_test():
    try:
        return await test_plc_connection()
    except Exception as exc:
        logger.exception("OPC UA connection test failed")
        raise HTTPException(
            status_code=502,
            detail=f"OPC UA test failed: {type(exc).__name__}: {exc}",
        ) from exc

dashboard_dir = BASE_DIR / "dashboard"
if dashboard_dir.is_dir():
    app.mount(
        "/dashboard",
        StaticFiles(directory=dashboard_dir, html=True),
        name="dashboard",
    )