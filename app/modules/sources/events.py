import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import lru_cache

import redis
import redis.asyncio as aioredis

from app.modules.sources.models import Source
from app.modules.sources.schemas import SourceOut
from app.shared.config import get_settings

logger = logging.getLogger(__name__)


def channel_for(session_id: uuid.UUID) -> str:
    return f"sources:events:{session_id}"


@lru_cache
def _publisher(url: str) -> redis.Redis:
    return redis.Redis.from_url(url)


def publish_source_event(source: Source) -> None:
    """Tells everyone listening to the session that this source changed.

    Called after the change is committed, so a listener that reads the database right after
    the event always sees the new state. Never raises: a lost notification must not undo or
    fail the change itself (clients can reload the list).
    """
    source_id = getattr(source, "id", None)  # read first: the handler below must not fail
    try:
        payload = json.dumps(SourceOut.model_validate(source).model_dump(mode="json"))
        _publisher(get_settings().redis_url).publish(channel_for(source.session_id), payload)
    except Exception:
        logger.warning("Could not publish event for source %s", source_id, exc_info=True)


def format_sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


async def stream_events(
    session_id: uuid.UUID,
    load_snapshot: Callable[[], Awaitable[list[dict]]],
    heartbeat_seconds: float,
) -> AsyncIterator[str]:
    """Yields SSE messages: one `snapshot` with all sources, then a `source` event per change.

    Subscribes BEFORE loading the snapshot. The other order has a gap in which a change would
    be neither in the snapshot nor delivered. With this order the worst case is that a change
    appears twice (once in the snapshot, once as an event), which is harmless because every
    event carries the full latest state of one source.
    """
    client = aioredis.Redis.from_url(get_settings().redis_url)
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(channel_for(session_id))
        yield format_sse("snapshot", json.dumps({"sources": await load_snapshot()}))
        loop = asyncio.get_running_loop()
        last_sent = loop.time()
        while True:
            message = await pubsub.get_message(timeout=heartbeat_seconds)
            if message is not None:
                data = message["data"]
                yield format_sse("source", data.decode() if isinstance(data, bytes) else data)
                last_sent = loop.time()
            elif loop.time() - last_sent >= heartbeat_seconds - 0.01:
                # A comment line: ignored by clients, but keeps proxies from closing the idle
                # connection and lets us notice a dead client.
                yield ": keepalive\n\n"
                last_sent = loop.time()
    finally:
        # Also runs when the client disconnects and the stream gets cancelled.
        await pubsub.aclose()
        await client.aclose()
