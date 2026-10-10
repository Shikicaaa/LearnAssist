import asyncio
import contextlib
import json
import socket
import threading
import time
import uuid

import anyio
import httpx
import pytest
import redis
import uvicorn

from app.main import app
from app.modules.sources import events
from app.modules.sources.events import channel_for, publish_source_event, stream_events
from app.shared.config import get_settings
from tests.files import make_scanned_pdf
from tests.helpers import API, add_text, new_session, signup, sql_one, upload


@pytest.fixture(scope="module")
def live_server():
    """A real uvicorn server in a thread: TestClient cannot consume an endless stream."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "test server did not start"
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return signup(client, "bob@example.com")


@pytest.fixture
def sid(client, alice):
    return new_session(client, alice)


@pytest.fixture
def redis_client():
    return redis.Redis.from_url(get_settings().redis_url)


def open_stream(base, headers, sid):
    return httpx.stream(
        "GET",
        f"{base}{API}/sessions/{sid}/sources/events",
        headers=headers,
        timeout=httpx.Timeout(10.0),
    )


def parse(lines, timeout=15):
    """Yields (event, data) pairs; fails instead of hanging if nothing arrives in time."""
    deadline = time.time() + timeout
    event = None
    for line in lines:
        assert time.time() < deadline, "timed out waiting for server-sent events"
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            yield event, json.loads(line.removeprefix("data:").strip())


def collect_until(stream, done):
    seen = []
    for item in stream:
        seen.append(item)
        if done(seen):
            return seen
    raise AssertionError("stream ended early")


def statuses(seen, source_id):
    return [d["status"] for e, d in seen if e == "source" and d["id"] == source_id]


def reached(source_id, *final):
    return lambda seen: any(
        e == "source" and d["id"] == source_id and d["status"] in final for e, d in seen
    )


class TestAccess:
    def test_requires_authentication(self, client, sid):
        assert client.get(f"{API}/sessions/{sid}/sources/events").status_code == 401

    def test_foreign_and_unknown_sessions_are_404(self, client, bob, sid):
        assert client.get(f"{API}/sessions/{sid}/sources/events", headers=bob).status_code == 404
        missing = f"{API}/sessions/{uuid.uuid4()}/sources/events"
        assert client.get(missing, headers=bob).status_code == 404


class TestLiveStream:
    def test_sends_a_snapshot_of_existing_sources_first(self, client, alice, sid, live_server):
        source = add_text(client, alice, sid, title="old", content="already here").json()
        with open_stream(live_server, alice, sid) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            event, data = next(parse(response.iter_lines()))
        assert event == "snapshot"
        assert [(s["id"], s["status"]) for s in data["sources"]] == [(source["id"], "ready")]

    def test_upload_is_reported_queued_then_processing_then_ready(
        self, client, alice, sid, live_server
    ):
        with open_stream(live_server, alice, sid) as response:
            lines = response.iter_lines()
            stream = parse(lines)
            event, data = next(stream)
            assert (event, data) == ("snapshot", {"sources": []})

            source = add_text(client, alice, sid, content="some notes to learn from").json()
            seen = collect_until(stream, reached(source["id"], "ready", "failed"))

        assert statuses(seen, source["id"]) == ["queued", "processing", "ready"]
        assert {e for e, _ in seen} == {"source"}
        assert seen[-1][1]["page_count"] is None and seen[-1][1]["error"] is None

    def test_failure_is_reported_with_its_message(self, client, alice, sid, live_server):
        with open_stream(live_server, alice, sid) as response:
            lines = response.iter_lines()
            stream = parse(lines)
            next(stream)
            scan = make_scanned_pdf().getvalue()
            [source] = upload(client, alice, sid, ("scan.pdf", scan)).json()
            seen = collect_until(stream, reached(source["id"], "ready", "failed"))
        assert statuses(seen, source["id"]) == ["queued", "processing", "failed"]
        assert "scan" in seen[-1][1]["error"]

    def test_reindex_and_delete_are_reported(self, client, alice, sid, live_server):
        source = add_text(client, alice, sid, content="notes to reindex and delete").json()
        with open_stream(live_server, alice, sid) as response:
            lines = response.iter_lines()
            stream = parse(lines)
            next(stream)
            client.post(f"{API}/sources/{source['id']}/reindex", headers=alice)
            seen = collect_until(stream, reached(source["id"], "ready"))
            assert statuses(seen, source["id"]) == ["queued", "processing", "ready"]

            client.delete(f"{API}/sources/{source['id']}", headers=alice)
            seen = collect_until(stream, reached(source["id"], "deleted"))
            assert statuses(seen, source["id"]) == ["deleted"]

    def test_events_have_the_same_shape_as_the_rest_api(self, client, alice, sid, live_server):
        with open_stream(live_server, alice, sid) as response:
            lines = response.iter_lines()
            stream = parse(lines)
            next(stream)
            source = add_text(client, alice, sid, content="shape check").json()
            seen = collect_until(stream, reached(source["id"], "ready"))
        rest = client.get(f"{API}/sources/{source['id']}", headers=alice).json()
        assert seen[-1][1] == rest

    def test_every_listener_of_a_session_gets_the_events(self, client, alice, sid, live_server):
        with contextlib.ExitStack() as stack:
            streams = [stack.enter_context(open_stream(live_server, alice, sid)) for _ in range(3)]
            parsed = [parse(r.iter_lines()) for r in streams]
            for stream in parsed:
                next(stream)
            source = add_text(client, alice, sid, content="broadcast").json()
            for stream in parsed:
                seen = collect_until(stream, reached(source["id"], "ready"))
                assert statuses(seen, source["id"]) == ["queued", "processing", "ready"]

    def test_other_users_sessions_stay_silent(
        self, client, alice, bob, sid, live_server, monkeypatch
    ):
        monkeypatch.setattr(get_settings(), "sse_heartbeat_seconds", 0.3)
        bobs_session = new_session(client, bob, "Bob's")
        with open_stream(live_server, bob, bobs_session) as response:
            lines = response.iter_lines()
            stream = parse(lines)
            next(stream)
            add_text(client, alice, sid, content="alice only")
            deadline = time.time() + 1.5
            for line in lines:
                assert not line.startswith("event: source"), "received another user's event"
                if time.time() > deadline:
                    break

    def test_idle_connection_gets_keepalive_comments(
        self, client, alice, sid, live_server, monkeypatch
    ):
        monkeypatch.setattr(get_settings(), "sse_heartbeat_seconds", 0.3)
        with open_stream(live_server, alice, sid) as response:
            lines = response.iter_lines()
            next(parse(lines))
            deadline = time.time() + 5
            for line in lines:
                if line.startswith(": keepalive"):
                    return
                assert time.time() < deadline, "no keepalive received"

    def test_stream_does_not_hold_a_database_connection(self, client, alice, sid, live_server):
        with open_stream(live_server, alice, sid) as response:
            lines = response.iter_lines()  # keep a reference: dropping it closes the stream
            next(parse(lines))
            time.sleep(0.3)
            idle = sql_one(
                "SELECT count(*) FROM pg_stat_activity"
                " WHERE datname = current_database() AND state LIKE 'idle in transaction%'"
            )
        assert idle == 0

    def test_subscription_is_removed_when_the_client_disconnects(
        self, client, alice, sid, live_server, redis_client
    ):
        channel = channel_for(uuid.UUID(sid))
        with open_stream(live_server, alice, sid) as response:
            lines = response.iter_lines()  # keep a reference: dropping it closes the stream
            next(parse(lines))
            assert redis_client.pubsub_numsub(channel)[0][1] == 1
        deadline = time.time() + 5
        while redis_client.pubsub_numsub(channel)[0][1] and time.time() < deadline:
            time.sleep(0.1)
        assert redis_client.pubsub_numsub(channel)[0][1] == 0


async def wait_subscribed(redis_client, channel):
    for _ in range(100):
        if redis_client.pubsub_numsub(channel)[0][1] >= 1:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("never subscribed")


async def snapshot_of(*sources):
    return list(sources)


class TestStreamGenerator:
    async def test_snapshot_comes_first_then_events_in_order(self, redis_client):
        session_id = uuid.uuid4()
        stream = stream_events(session_id, lambda: snapshot_of({"id": "a"}), heartbeat_seconds=5)
        try:
            first = await stream.__anext__()
            assert first == 'event: snapshot\ndata: {"sources": [{"id": "a"}]}\n\n'
            for n in (1, 2):
                redis_client.publish(channel_for(session_id), json.dumps({"n": n}))
            assert await stream.__anext__() == 'event: source\ndata: {"n": 1}\n\n'
            assert await stream.__anext__() == 'event: source\ndata: {"n": 2}\n\n'
        finally:
            await stream.aclose()

    async def test_a_change_during_the_snapshot_load_is_not_lost(self, redis_client):
        session_id = uuid.uuid4()

        async def slow_snapshot():
            # Simulates a change happening between "start listening" and "snapshot is read".
            redis_client.publish(channel_for(session_id), json.dumps({"during": "snapshot"}))
            return []

        stream = stream_events(session_id, slow_snapshot, heartbeat_seconds=5)
        try:
            assert (await stream.__anext__()).startswith("event: snapshot")
            assert await stream.__anext__() == 'event: source\ndata: {"during": "snapshot"}\n\n'
        finally:
            await stream.aclose()

    async def test_events_of_other_sessions_are_not_delivered(self, redis_client):
        mine, other = uuid.uuid4(), uuid.uuid4()
        stream = stream_events(mine, lambda: snapshot_of(), heartbeat_seconds=5)
        try:
            await stream.__anext__()
            redis_client.publish(channel_for(other), json.dumps({"from": "other"}))
            redis_client.publish(channel_for(mine), json.dumps({"from": "mine"}))
            assert await stream.__anext__() == 'event: source\ndata: {"from": "mine"}\n\n'
        finally:
            await stream.aclose()

    async def test_keepalive_is_sent_when_idle(self):
        stream = stream_events(uuid.uuid4(), lambda: snapshot_of(), heartbeat_seconds=0.2)
        try:
            await stream.__anext__()
            assert await asyncio.wait_for(stream.__anext__(), 2) == ": keepalive\n\n"
        finally:
            await stream.aclose()

    async def test_cleanup_survives_cancellation_of_the_enclosing_scope(self, redis_client):
        """Starlette cancels the stream with an anyio scope when the client leaves; the Redis
        subscription must still be released (guards against library behaviour changing)."""
        session_id = uuid.uuid4()
        channel = channel_for(session_id)
        scopes = []

        async def consume():
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                async for _ in stream_events(session_id, lambda: snapshot_of(), 5):
                    pass

        task = asyncio.create_task(consume())
        await wait_subscribed(redis_client, channel)
        scopes[0].cancel()
        await asyncio.wait_for(task, 5)
        assert redis_client.pubsub_numsub(channel)[0][1] == 0


class TestPublisher:
    def test_a_redis_outage_never_breaks_the_operation(self, client, alice, sid, monkeypatch):
        class Broken:
            def publish(self, *args):
                raise redis.ConnectionError("redis is down")

        monkeypatch.setattr(events, "_publisher", lambda url: Broken())
        r = add_text(client, alice, sid, content="still works without redis events")
        assert r.status_code == 202 and r.json()["status"] == "ready"

    def test_publish_function_swallows_errors(self, monkeypatch):
        monkeypatch.setattr(events, "_publisher", lambda url: (_ for _ in ()).throw(OSError()))
        publish_source_event(object())  # not even a real source: must not raise
