import os
import subprocess
import sys

import psycopg
import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

DB_NAME = "rag_migration_test"
_dev_url = make_url(
    dotenv_values(".env")
    .get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    .replace("postgresql://", "postgresql+psycopg://", 1)
)
_scratch_url = _dev_url.set(database=DB_NAME)


def alembic(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": _scratch_url.render_as_string(hide_password=False)}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def empty_database():
    admin = _dev_url.set(database="postgres", drivername="postgresql+psycopg")
    admin = admin.render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {DB_NAME}")
    yield
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)")


def test_migrations(empty_database):
    upgrade = alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    check = alembic("check")
    assert check.returncode == 0, check.stdout + check.stderr


def test_migrations_can_be_undone(empty_database):
    upgrade = alembic("upgrade", "head")
    assert upgrade.returncode == 0

    downgrade = alembic("downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr
