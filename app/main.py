from fastapi import FastAPI

from app.modules import auth, sessions
from app.shared import health
from app.shared.errors import register_error_handlers

app = FastAPI(title="RAG Learning")
register_error_handlers(app)
app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
