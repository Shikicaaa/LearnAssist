"""Public interface of the chat module: other modules may import only this."""

from app.modules.chat.api import router
from app.modules.chat.prompts import PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "router"]
