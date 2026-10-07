import hashlib
import secrets
import uuid
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.shared.config import get_settings
from app.shared.db import utcnow
from app.shared.errors import UnauthorizedError

_hasher = PasswordHasher()
# Hash lažne lozinke: koristi se kad email ne postoji, da login traje isto kao za pravog korisnika.
_DUMMY_HASH = _hasher.hash("lazna-lozinka-za-izjednacavanje-vremena")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def burn_password_check(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise UnauthorizedError("Invalid or expired token") from None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    # SHA-256 je dovoljan jer je token nasumičan sa visokom entropijom (za razliku od lozinke).
    return hashlib.sha256(raw.encode()).hexdigest()
