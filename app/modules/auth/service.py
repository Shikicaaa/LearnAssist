import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth import security
from app.modules.auth.models import User
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import TokenPair
from app.shared.config import get_settings
from app.shared.db import utcnow
from app.shared.errors import BadRequestError, ConflictError, UnauthorizedError


def normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AuthRepository(db)

    def register(self, email: str, password: str) -> User:
        email = normalize_email(email)
        if self.repo.get_user_by_email(email):
            raise ConflictError("An account with this email already exists")
        try:
            user = self.repo.add_user(email, security.hash_password(password))
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ConflictError("An account with this email already exists") from None
        return user

    def login(self, email: str, password: str) -> TokenPair:
        user = self.repo.get_user_by_email(normalize_email(email))
        if user is None:
            security.burn_password_check(password)
            raise UnauthorizedError("Wrong email or password")
        password_ok = security.verify_password(user.password_hash, password)
        if not password_ok or not user.is_active:
            raise UnauthorizedError("Wrong email or password")
        return self._issue_tokens(user.id)

    def refresh(self, raw_refresh_token: str) -> TokenPair:
        token = self.repo.get_refresh_token_for_update(
            security.hash_refresh_token(raw_refresh_token)
        )
        if token is None:
            raise UnauthorizedError("Invalid refresh token")
        now = utcnow()
        if token.revoked_at is not None:
            self.repo.revoke_all_tokens(token.user_id, now)
            self.db.commit()
            raise UnauthorizedError("Refresh token has already been used")
        if token.expires_at <= now:
            raise UnauthorizedError("Refresh token has expired")
        user = self.repo.get_user_by_id(token.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Account is not active")
        token.revoked_at = now
        return self._issue_tokens(user.id)

    def logout(self, user_id: uuid.UUID, raw_refresh_token: str) -> None:
        token = self.repo.get_refresh_token_for_update(
            security.hash_refresh_token(raw_refresh_token)
        )
        if token is not None and token.user_id == user_id and token.revoked_at is None:
            token.revoked_at = utcnow()
        self.db.commit()

    def change_password(self, user_id: uuid.UUID, old_password: str, new_password: str) -> None:
        user = self.repo.get_user_by_id(user_id)
        if user is None or not security.verify_password(user.password_hash, old_password):
            raise BadRequestError("Current password is incorrect")
        user.password_hash = security.hash_password(new_password)
        self.repo.revoke_all_tokens(user.id, utcnow())
        self.db.commit()

    def get_user(self, user_id: uuid.UUID) -> User | None:
        return self.repo.get_user_by_id(user_id)

    def _issue_tokens(self, user_id: uuid.UUID) -> TokenPair:
        settings = get_settings()
        raw = security.new_refresh_token()
        self.repo.add_refresh_token(
            user_id,
            security.hash_refresh_token(raw),
            utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
        self.db.commit()
        return TokenPair(
            access_token=security.create_access_token(user_id),
            refresh_token=raw,
            expires_in=settings.access_token_expire_minutes * 60,
        )
