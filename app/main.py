import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.modules import auth, chat, llm, sessions, sources
from app.modules.embeddings import get_embedder
from app.shared import health
from app.shared.config import get_settings
from app.shared.errors import register_error_handlers

logger = logging.getLogger(__name__)


def _warm_up_embedder() -> None:
    try:
        get_embedder().embed_query("warm up")
    except Exception:
        logger.warning("Could not warm up the embedding model", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading the model takes ~10-20 s. Do it in the background right at startup, so the first
    # question of the first user does not pay for it.
    if get_settings().warm_up_embedder:
        threading.Thread(target=_warm_up_embedder, daemon=True).start()
    yield


app = FastAPI(title="RAG Learning", lifespan=lifespan)
register_error_handlers(app)
app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(llm.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
