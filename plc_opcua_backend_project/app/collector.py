import asyncio
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from asyncua import ua
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import Reading
from app.plc_client import create_plc_client

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReadingEvent:
    node_id: str
    value: Any
    value_type: str
    status_code: str
    source_timestamp: datetime | None
    received_at: datetime


def json_safe(value: Any) -> Any:
    """Convert OPC UA values into values that can be stored as JSON."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class SubscriptionHandler:
    def __init__(self, queue: asyncio.Queue[ReadingEvent | None]):
        self.queue = queue

    def datachange_notification(self, node, value, data):
        try:
            monitored_value = getattr(getattr(data, "monitored_item", None), "Value", None)
            status = getattr(monitored_value, "StatusCode", None)
            source_timestamp = getattr(monitored_value, "SourceTimestamp", None)
            if source_timestamp is not None and source_timestamp.tzinfo is None:
                source_timestamp = source_timestamp.replace(tzinfo=timezone.utc)

            event = ReadingEvent(
                node_id=node.nodeid.to_string(),
                value=json_safe(value),
                value_type=type(value).__name__,
                status_code=str(status) if status is not None else "Unknown",
                source_timestamp=source_timestamp,
                received_at=datetime.now(timezone.utc),
            )
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error("Reading queue is full; a notification was dropped.")
        except Exception:
            logger.exception("Could not enqueue an OPC UA data-change notification.")


async def database_writer(queue: asyncio.Queue[ReadingEvent | None]) -> None:
    while True:
        event = await queue.get()
        try:
            if event is None:
                return
            async with SessionLocal() as session:
                session.add(
                    Reading(
                        node_id=event.node_id,
                        value=event.value,
                        value_type=event.value_type,
                        status_code=event.status_code,
                        source_timestamp=event.source_timestamp,
                        received_at=event.received_at,
                    )
                )
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to save an OPC UA reading to PostgreSQL.")
        finally:
            queue.task_done()


def configured_node_ids() -> list[str]:
    raw = os.getenv("OPCUA_NODE_IDS", "").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


async def run_collector(queue: asyncio.Queue[ReadingEvent | None]) -> None:
    node_ids = configured_node_ids()
    if not node_ids:
        logger.warning("OPCUA_NODE_IDS is blank; collector is not starting.")
        return

    interval_ms = int(os.getenv("OPCUA_SUBSCRIPTION_INTERVAL_MS", "1000"))
    if interval_ms < 100:
        raise RuntimeError("OPCUA_SUBSCRIPTION_INTERVAL_MS must be at least 100.")

    while True:
        try:
            client = await create_plc_client()
            async with client:
                nodes = [client.get_node(node_id) for node_id in node_ids]
                # Fail fast if a configured NodeId is invalid or unreadable.
                for node in nodes:
                    await node.read_data_value()

                handler = SubscriptionHandler(queue)
                subscription = await client.create_subscription(interval_ms, handler)
                await subscription.subscribe_data_change(nodes)
                logger.info("Subscribed to %d OPC UA node(s).", len(nodes))

                try:
                    # Notifications are subscription-driven. This periodic read of the
                    # first node is only a lightweight connection watchdog.
                    while True:
                        await asyncio.sleep(10)
                        await nodes[0].read_data_value()
                finally:
                    try:
                        await subscription.delete()
                    except Exception:
                        logger.debug("Subscription cleanup failed.", exc_info=True)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("OPC UA collector failed; retrying in 5 seconds.")
            await asyncio.sleep(5)
