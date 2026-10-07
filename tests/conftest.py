import os

import psycopg
import pytest
import redis
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

_dev_url = make_url(
    dotenv_values(".env")["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
)
_test_url = _dev_url.set(database="rag_test")

# Mora pre uvoza app: engine se pravi pri uvozu i čita ove promenljive.
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["RATE_LIMIT_AUTH_REQUESTS"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.main import app  # noqa: E402
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


@pytest.fixture
def client():
    return TestClient(app)
