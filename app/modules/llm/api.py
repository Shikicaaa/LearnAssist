import time

from fastapi import APIRouter, Depends

from app.modules.auth import UserOut, get_current_user
from app.modules.llm.schemas import LLMTestRequest, LLMTestResponse
from app.modules.llm.service import LLMMessage, LLMProvider, get_llm_provider
from app.shared.config import get_settings
from app.shared.errors import NotFoundError
from app.shared.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/llm", tags=["llm (development only)"])


def require_development() -> None:
    # A raw "talk to the model" endpoint spends quota and bypasses our source-only prompt,
    # so it exists only on development machines.
    if get_settings().environment != "development":
        raise NotFoundError("Not found")


@router.post(
    "/test", response_model=LLMTestResponse, dependencies=[Depends(require_development)]
)
def test_llm(
    body: LLMTestRequest,
    user: UserOut = Depends(get_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
):
    enforce_rate_limit(
        f"rl:llm_test:{user.id}",
        limit=get_settings().llm_test_requests_per_minute,
        window_seconds=60,
    )
    started = time.perf_counter()
    result = provider.generate(
        [LLMMessage("user", body.message)], system=body.system, max_output_tokens=2048
    )
    return LLMTestResponse(
        answer=result.text,
        provider=result.provider,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
