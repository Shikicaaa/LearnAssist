import redis

from app.shared.config import get_settings
from app.shared.errors import RateLimitError


def enforce_rate_limit(key: str) -> None:
    """Fiksni prozor: INCR brojač pod ključem, prvi put postavi istek. Preko limita -> 429."""
    settings = get_settings()
    client = redis.Redis.from_url(settings.redis_url)
    window = settings.rate_limit_auth_window_seconds
    count = client.incr(key)
    if count == 1:
        client.expire(key, window)
    if count > settings.rate_limit_auth_requests:
        raise RateLimitError("Too many attempts. Please try again in a moment.")
