"""Public interface of the cache module: other modules may import only this."""

from app.modules.cache.api import router
from app.modules.cache.schemas import CacheContext, CachedCitation, CacheHit
from app.modules.cache.service import clear_session, lookup, store

__all__ = [
    "CacheContext",
    "CacheHit",
    "CachedCitation",
    "clear_session",
    "lookup",
    "router",
    "store",
]
