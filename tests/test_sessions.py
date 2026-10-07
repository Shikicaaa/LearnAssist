import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.modules.sessions import bump_corpus_version
from app.shared.config import get_settings
from app.shared.db import SessionLocal, engine

API = "/api/v1/sessions"


def signup(client, email: str) -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": "tajna-lozinka-123"})
    tokens = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "tajna-lozinka-123"}
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return signup(client, "bob@example.com")


def create(client, headers, title="Analiza 1"):
    return client.post(API, json={"title": title}, headers=headers)


class TestCreate:
    def test_creates_session_with_defaults(self, client, alice):
        r = create(client, alice)
        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "Analiza 1"
        assert body["corpus_version"] == 0
        assert body["cache_enabled"] is True
        assert body["embedding_model"] == get_settings().embedding_model

    def test_requires_authentication(self, client):
        assert client.post(API, json={"title": "x"}).status_code == 401

    @pytest.mark.parametrize("title", ["", "   ", "x" * 201])
    def test_invalid_title_is_422(self, client, alice, title):
        assert create(client, alice, title=title).status_code == 422

    def test_title_is_stripped(self, client, alice):
        assert create(client, alice, title="  Fizika  ").json()["title"] == "Fizika"


class TestList:
    def test_returns_only_own_sessions_newest_first(self, client, alice, bob):
        create(client, alice, "prva")
        create(client, alice, "druga")
        create(client, bob, "bobova")
        body = client.get(API, headers=alice).json()
        assert [s["title"] for s in body["items"]] == ["druga", "prva"]
        assert body["total"] == 2

    def test_pagination(self, client, alice):
        for i in range(5):
            create(client, alice, f"s{i}")
        page = client.get(API, params={"limit": 2, "offset": 2}, headers=alice).json()
        assert [s["title"] for s in page["items"]] == ["s2", "s1"]
        assert page["total"] == 5 and page["limit"] == 2 and page["offset"] == 2

    def test_limit_above_maximum_is_422(self, client, alice):
        assert client.get(API, params={"limit": 1000}, headers=alice).status_code == 422


class TestOwnership:
    def test_get_own_session(self, client, alice):
        sid = create(client, alice).json()["id"]
        assert client.get(f"{API}/{sid}", headers=alice).status_code == 200

    def test_foreign_and_missing_sessions_are_indistinguishable_404(self, client, alice, bob):
        sid = create(client, alice).json()["id"]
        foreign = client.get(f"{API}/{sid}", headers=bob)
        missing = client.get(f"{API}/{uuid.uuid4()}", headers=bob)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()

    def test_cannot_patch_foreign_session(self, client, alice, bob):
        sid = create(client, alice).json()["id"]
        r = client.patch(f"{API}/{sid}", json={"title": "hakovano"}, headers=bob)
        assert r.status_code == 404
        assert client.get(f"{API}/{sid}", headers=alice).json()["title"] == "Analiza 1"

    def test_cannot_delete_foreign_session(self, client, alice, bob):
        sid = create(client, alice).json()["id"]
        assert client.delete(f"{API}/{sid}", headers=bob).status_code == 404
        assert client.get(f"{API}/{sid}", headers=alice).status_code == 200

    def test_invalid_uuid_is_422(self, client, alice):
        assert client.get(f"{API}/nije-uuid", headers=alice).status_code == 422


class TestUpdate:
    def test_updates_title_and_cache_flag(self, client, alice):
        sid = create(client, alice).json()["id"]
        r = client.patch(
            f"{API}/{sid}", json={"title": "Nova", "cache_enabled": False}, headers=alice
        )
        assert r.status_code == 200
        assert r.json()["title"] == "Nova" and r.json()["cache_enabled"] is False

    def test_partial_update_keeps_other_fields(self, client, alice):
        sid = create(client, alice).json()["id"]
        r = client.patch(f"{API}/{sid}", json={"cache_enabled": False}, headers=alice)
        assert r.json()["title"] == "Analiza 1"

    def test_client_cannot_set_corpus_version(self, client, alice):
        sid = create(client, alice).json()["id"]
        client.patch(f"{API}/{sid}", json={"corpus_version": 99}, headers=alice)
        assert client.get(f"{API}/{sid}", headers=alice).json()["corpus_version"] == 0


class TestDelete:
    def test_deletes_session(self, client, alice):
        sid = create(client, alice).json()["id"]
        assert client.delete(f"{API}/{sid}", headers=alice).status_code == 204
        assert client.get(f"{API}/{sid}", headers=alice).status_code == 404

    def test_deleting_user_removes_their_sessions(self, client, alice):
        create(client, alice)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users"))
            assert conn.execute(text("SELECT count(*) FROM sessions")).scalar_one() == 0


class TestQuota:
    @pytest.fixture(autouse=True)
    def small_limit(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_sessions_per_user", 3)

    def test_limit_returns_429(self, client, alice):
        assert [create(client, alice).status_code for _ in range(4)] == [201, 201, 201, 429]
        assert create(client, alice).json()["error"]["code"] == "quota_exceeded"

    def test_limit_is_per_user(self, client, alice, bob):
        for _ in range(3):
            create(client, alice)
        assert create(client, bob).status_code == 201

    def test_deleting_frees_a_slot(self, client, alice):
        ids = [create(client, alice).json()["id"] for _ in range(3)]
        client.delete(f"{API}/{ids[0]}", headers=alice)
        assert create(client, alice).status_code == 201

    def test_concurrent_creates_cannot_exceed_limit(self, alice):
        def attempt(_):
            return create(TestClient(app), alice).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(attempt, range(12)))
        assert statuses.count(201) == 3
        assert statuses.count(429) == 9


class TestCorpusVersion:
    def test_bump_increments_and_is_visible(self, client, alice):
        sid = uuid.UUID(create(client, alice).json()["id"])
        with SessionLocal() as db:
            assert bump_corpus_version(db, sid) == 1
            assert bump_corpus_version(db, sid) == 2
            db.commit()
        assert client.get(f"{API}/{sid}", headers=alice).json()["corpus_version"] == 2

    def test_concurrent_bumps_are_not_lost(self, client, alice):
        sid = uuid.UUID(create(client, alice).json()["id"])

        def bump(_):
            with SessionLocal() as db:
                bump_corpus_version(db, sid)
                db.commit()

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(bump, range(20)))
        assert client.get(f"{API}/{sid}", headers=alice).json()["corpus_version"] == 20

    def test_bump_unknown_session_raises(self):
        from app.shared.errors import NotFoundError

        with SessionLocal() as db, pytest.raises(NotFoundError):
            bump_corpus_version(db, uuid.uuid4())

    def test_bump_does_not_commit_on_its_own(self, client, alice):
        sid = uuid.UUID(create(client, alice).json()["id"])
        with SessionLocal() as db:
            bump_corpus_version(db, sid)
            db.rollback()
        assert client.get(f"{API}/{sid}", headers=alice).json()["corpus_version"] == 0
