import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from app.collector import database_writer, run_collector  # noqa: E402
from app.database import SessionLocal, check_database, engine, get_session  # noqa: E402
from app.models import Base, Reading  # noqa: E402
from app.plc_client import test_plc_connection  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
    writer_task = asyncio.create_task(database_writer(queue), name="postgres-writer")

    collector_task = None
    if os.getenv("OPCUA_NODE_IDS", "").strip():
        collector_task = asyncio.create_task(run_collector(queue), name="opcua-collector")
    else:
        logger.warning("OPCUA_NODE_IDS is blank. API/database start, OPC UA collector is disabled.")

    app.state.reading_queue = queue
    try:
        yield
    finally:
        if collector_task:
            collector_task.cancel()
            try:
                await collector_task
            except asyncio.CancelledError:
                pass

        # Let queued readings finish before shutting down the writer.
        try:
            await asyncio.wait_for(queue.join(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for queued readings during shutdown.")

        await queue.put(None)
        try:
            await asyncio.wait_for(writer_task, timeout=5)
        except asyncio.TimeoutError:
            writer_task.cancel()
        await engine.dispose()


app = FastAPI(
    title="PLC Monitoring Backend",
    version="1.0.0",
    description="Read-only OPC UA collector, PostgreSQL storage, and monitoring API.",
    lifespan=lifespan,
)


@app.get("/")
async def home():
    return {
        "application": "PLC Monitoring Backend",
        "status": "running",
        "collector_enabled": bool(os.getenv("OPCUA_NODE_IDS", "").strip()),
        "docs": "/docs",
        "dashboard": "/dashboard/",
    }


@app.get("/health/db")
async def database_health():
    try:
        await check_database()
        return {"database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database check failed: {type(exc).__name__}") from exc


@app.get("/plc/test")
async def plc_test():
    try:
        return await test_plc_connection()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/readings/latest")
async def latest_readings(
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Reading).order_by(Reading.received_at.desc()).limit(limit)
    )
    rows = result.scalars().all()
    return [reading_to_dict(row) for row in rows]


@app.get("/readings/history")
async def reading_history(
    node_id: str = Query(..., min_length=1, max_length=512),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Reading)
        .where(Reading.node_id == node_id)
        .order_by(Reading.received_at.desc())
        .limit(limit)
    )
    return [reading_to_dict(row) for row in result.scalars().all()]


def reading_to_dict(row: Reading) -> dict:
    return {
        "id": row.id,
        "node_id": row.node_id,
        "value": row.value,
        "value_type": row.value_type,
        "status_code": row.status_code,
        "source_timestamp": row.source_timestamp.isoformat() if row.source_timestamp else None,
        "received_at": row.received_at.isoformat() if row.received_at else None,
    }


dashboard_dir = BASE_DIR / "dashboard"
if dashboard_dir.is_dir():
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")
