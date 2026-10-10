import redis

from app.shared.config import get_settings
from app.shared.errors import RateLimitError


def enforce_rate_limit(
    key: str, limit: int | None = None, window_seconds: int | None = None
) -> None:
    """Fixed-window counter in Redis; defaults to the auth limits from the settings."""
    settings = get_settings()
    limit = limit if limit is not None else settings.rate_limit_auth_requests
    window = (
        window_seconds if window_seconds is not None else settings.rate_limit_auth_window_seconds
    )
    client = redis.Redis.from_url(settings.redis_url)
    count = client.incr(key)
    if count == 1:
        client.expire(key, window)
    if count > limit:
        raise RateLimitError("Too many attempts. Please try again in a moment.")
