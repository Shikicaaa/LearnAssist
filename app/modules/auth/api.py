from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.modules.auth import security
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.modules.auth.service import AuthService, normalize_email
from app.shared.db import get_db
from app.shared.errors import UnauthorizedError
from app.shared.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    if credentials is None:
        raise UnauthorizedError("Missing token")
    user = service.get_user(security.decode_access_token(credentials.credentials))
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is not active")
    return UserOut.model_validate(user)


def _limit_by_ip_and_email(request: Request, route: str, email: str) -> None:
    ip = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"rl:auth:{route}:ip:{ip}")
    enforce_rate_limit(f"rl:auth:{route}:email:{normalize_email(email)}")


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    body: RegisterRequest, request: Request, service: AuthService = Depends(get_auth_service)
):
    _limit_by_ip_and_email(request, "register", body.email)
    return service.register(body.email, body.password)


@router.post("/login", response_model=TokenPair)
def login(body: LoginRequest, request: Request, service: AuthService = Depends(get_auth_service)):
    _limit_by_ip_and_email(request, "login", body.email)
    return service.login(body.email, body.password)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    return service.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
def logout(
    body: RefreshRequest,
    user: UserOut = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.logout(user.id, body.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    user: UserOut = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.change_password(user.id, body.old_password, body.new_password)
    return Response(status_code=204)
