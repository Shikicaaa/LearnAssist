import atexit
import os
import shutil
import tempfile
from pathlib import Path

import psycopg
import pytest
import redis
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

_dev_url = make_url(
    dotenv_values(".env")["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
)
_test_url = _dev_url.set(database="rag_test")
STORAGE_DIR = Path(tempfile.mkdtemp(prefix="rag_test_files_"))
atexit.register(shutil.rmtree, STORAGE_DIR, ignore_errors=True)

# Must be set before importing app: the engine is created at import time and reads these.
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["RATE_LIMIT_AUTH_REQUESTS"] = "1000"
os.environ["LOCAL_STORAGE_PATH"] = str(STORAGE_DIR)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.main import app  # noqa: E402
from app.modules.embeddings import FakeEmbedder  # noqa: E402
from app.modules.jobs import InlineTaskQueue, get_task_queue  # noqa: E402
from app.modules.sources import tasks as source_tasks  # noqa: E402
from app.shared.db import Base, engine  # noqa: E402


def _create_test_database() -> None:
    admin_url = _dev_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'rag_test'").fetchone()
        if not exists:
            conn.execute("CREATE DATABASE rag_test")


@pytest.fixture(scope="session", autouse=True)
def database():
    _create_test_database()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_state(database):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
    redis.Redis.from_url(os.environ["REDIS_URL"]).flushdb()
    for child in STORAGE_DIR.iterdir():
        shutil.rmtree(child, ignore_errors=True)


@pytest.fixture(autouse=True)
def fake_services(monkeypatch):
    """No broker, no worker, no model: tasks run inline and embeddings are computed by a fake."""
    embedder = FakeEmbedder()
    monkeypatch.setattr(source_tasks, "get_embedder", lambda: embedder)
    app.dependency_overrides[get_task_queue] = InlineTaskQueue
    yield embedder
    app.dependency_overrides.pop(get_task_queue, None)


@pytest.fixture
def client():
    return TestClient(app)
