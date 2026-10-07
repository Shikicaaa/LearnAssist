from datetime import timedelta

import jwt
import pytest
from sqlalchemy import text

from app.shared.config import get_settings
from app.shared.db import engine, utcnow

EMAIL = "student@example.com"
PASSWORD = "tajna-lozinka-123"
API = "/api/v1/auth"


def register(client, email=EMAIL, password=PASSWORD):
    return client.post(f"{API}/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post(f"{API}/login", json={"email": email, "password": password})


def auth_header(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def tokens(client):
    register(client)
    return login(client).json()


class TestRegister:
    def test_creates_user_without_exposing_password(self, client):
        r = register(client)
        assert r.status_code == 201
        assert r.json()["email"] == EMAIL
        assert "password" not in r.text and "password_hash" not in r.text

    def test_duplicate_email_is_409_case_insensitive(self, client):
        register(client)
        r = register(client, email="Student@Example.COM")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "conflict"

    def test_short_password_is_422_in_standard_error_format(self, client):
        r = register(client, password="kratka")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_invalid_email_is_422(self, client):
        assert register(client, email="nije-email").status_code == 422

    def test_password_is_stored_as_argon2_hash(self, client):
        register(client)
        with engine.connect() as conn:
            stored = conn.execute(text("SELECT password_hash FROM users")).scalar_one()
        assert stored.startswith("$argon2") and PASSWORD not in stored


class TestLogin:
    def test_returns_token_pair(self, client):
        register(client)
        r = login(client)
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"] and body["refresh_token"]

    def test_wrong_password_and_unknown_email_give_same_response(self, client):
        register(client)
        wrong = login(client, password="pogresna-lozinka")
        unknown = login(client, email="niko@example.com")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

    def test_refresh_token_is_stored_only_as_hash(self, client, tokens):
        with engine.connect() as conn:
            stored = conn.execute(text("SELECT token_hash FROM refresh_tokens")).scalars().all()
        assert tokens["refresh_token"] not in stored


class TestMe:
    def test_returns_current_user(self, client, tokens):
        r = client.get(f"{API}/me", headers=auth_header(tokens))
        assert r.status_code == 200
        assert r.json()["email"] == EMAIL

    def test_missing_token_is_401(self, client):
        assert client.get(f"{API}/me").status_code == 401

    def test_garbage_token_is_401(self, client):
        r = client.get(f"{API}/me", headers={"Authorization": "Bearer nesto.sto.nije.jwt"})
        assert r.status_code == 401

    def test_expired_access_token_is_401(self, client, tokens):
        settings = get_settings()
        sub = jwt.decode(tokens["access_token"], options={"verify_signature": False})["sub"]
        expired = jwt.encode(
            {"sub": sub, "exp": utcnow() - timedelta(minutes=1)},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_token_signed_with_other_key_is_401(self, client, tokens):
        sub = jwt.decode(tokens["access_token"], options={"verify_signature": False})["sub"]
        forged = jwt.encode(
            {"sub": sub, "exp": utcnow() + timedelta(minutes=5)},
            "x" * 40,
            algorithm="HS256",
        )
        r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {forged}"})
        assert r.status_code == 401


class TestRefresh:
    def test_rotation_returns_new_working_pair(self, client, tokens):
        r = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 200
        new = r.json()
        assert new["refresh_token"] != tokens["refresh_token"]
        assert client.get(f"{API}/me", headers=auth_header(new)).status_code == 200

    def test_old_refresh_token_cannot_be_reused(self, client, tokens):
        client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        r = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 401

    def test_reuse_revokes_the_whole_chain(self, client, tokens):
        new = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
        client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        r = client.post(f"{API}/refresh", json={"refresh_token": new["refresh_token"]})
        assert r.status_code == 401

    def test_unknown_token_is_401(self, client):
        assert client.post(f"{API}/refresh", json={"refresh_token": "nepostoji"}).status_code == 401

    def test_expired_token_is_401(self, client, tokens):
        with engine.begin() as conn:
            conn.execute(text("UPDATE refresh_tokens SET expires_at = now() - interval '1 day'"))
        r = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 401


class TestLogout:
    def test_revokes_refresh_token(self, client, tokens):
        r = client.post(
            f"{API}/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=auth_header(tokens),
        )
        assert r.status_code == 204
        again = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert again.status_code == 401

    def test_requires_authentication(self, client, tokens):
        r = client.post(f"{API}/logout", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 401

    def test_cannot_revoke_another_users_token(self, client, tokens):
        register(client, email="drugi@example.com")
        other = login(client, email="drugi@example.com").json()
        client.post(
            f"{API}/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=auth_header(other),
        )
        r = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r.status_code == 200


class TestChangePassword:
    def test_changes_password_and_revokes_all_refresh_tokens(self, client, tokens):
        r = client.post(
            f"{API}/change-password",
            json={"old_password": PASSWORD, "new_password": "nova-lozinka-456"},
            headers=auth_header(tokens),
        )
        assert r.status_code == 204
        assert login(client).status_code == 401
        assert login(client, password="nova-lozinka-456").status_code == 200
        old_refresh = client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert old_refresh.status_code == 401

    def test_wrong_old_password_is_400(self, client, tokens):
        r = client.post(
            f"{API}/change-password",
            json={"old_password": "pogresna", "new_password": "nova-lozinka-456"},
            headers=auth_header(tokens),
        )
        assert r.status_code == 400
        assert login(client).status_code == 200


class TestRateLimit:
    def test_login_is_limited_per_ip(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "rate_limit_auth_requests", 3)
        statuses = [login(client, email=f"u{i}@example.com").status_code for i in range(5)]
        assert statuses[:3] == [401, 401, 401]
        assert statuses[3:] == [429, 429]

    def test_login_is_limited_per_email(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "rate_limit_auth_requests", 3)
        register(client)
        wrong = [login(client, password="pogresna-lozinka").status_code for _ in range(4)]
        assert wrong[-1] == 429
