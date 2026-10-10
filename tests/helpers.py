import io
from pathlib import Path

from sqlalchemy import text

from app.shared.db import engine
from tests.conftest import STORAGE_DIR

API = "/api/v1"
PASSWORD = "tajna-lozinka-123"


def signup(client, email: str) -> dict:
    client.post(f"{API}/auth/register", json={"email": email, "password": PASSWORD})
    tokens = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def new_session(client, headers, title="Course") -> str:
    return client.post(f"{API}/sessions", json={"title": title}, headers=headers).json()["id"]


def upload(client, headers, sid, *files: tuple[str, bytes | io.BytesIO]):
    parts = [("files", (name, data, "application/octet-stream")) for name, data in files]
    return client.post(f"{API}/sessions/{sid}/sources/files", files=parts, headers=headers)


def add_text(client, headers, sid, title="Notes", content="Some pasted study notes."):
    body = {"title": title, "content": content}
    return client.post(f"{API}/sessions/{sid}/sources/text", json=body, headers=headers)


def corpus_version(client, headers, sid) -> int:
    return client.get(f"{API}/sessions/{sid}", headers=headers).json()["corpus_version"]


def sql(query: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(query), params).all()


def sql_one(query: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(query), params).scalar_one()


def stored_files() -> list[Path]:
    return [p for p in STORAGE_DIR.rglob("*") if p.is_file()]
