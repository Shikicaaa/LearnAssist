import uuid
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.chat.models import Message, MessageCitation


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_message(self, **fields) -> Message:
        message = Message(**fields)
        self.db.add(message)
        self.db.flush()
        return message

    def add_citations(self, citations: list[MessageCitation]) -> None:
        self.db.add_all(citations)
        self.db.flush()

    def recent(self, session_id: uuid.UUID, user_id: uuid.UUID, limit: int) -> list[Message]:
        """The last `limit` messages, oldest first (the order a conversation is read in)."""
        stmt = (
            select(Message)
            .where(Message.session_id == session_id, Message.user_id == user_id)
            .order_by(Message.created_at.desc(), Message.id)
            .limit(limit)
        )
        return list(reversed(list(self.db.scalars(stmt))))

    def page(
        self, session_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Message], int]:
        where = (Message.session_id == session_id, Message.user_id == user_id)
        stmt = (
            select(Message)
            .where(*where)
            .order_by(Message.created_at.desc(), Message.id)
            .limit(limit)
            .offset(offset)
        )
        total = self.db.scalar(select(func.count()).select_from(Message).where(*where)) or 0
        return list(self.db.scalars(stmt)), total

    def citations_for(self, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[MessageCitation]]:
        grouped: dict[uuid.UUID, list[MessageCitation]] = defaultdict(list)
        if not message_ids:
            return grouped
        stmt = (
            select(MessageCitation)
            .where(MessageCitation.message_id.in_(message_ids))
            .order_by(MessageCitation.rank)
        )
        for citation in self.db.scalars(stmt):
            grouped[citation.message_id].append(citation)
        return grouped

    def delete_all(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.db.execute(
            delete(Message).where(Message.session_id == session_id, Message.user_id == user_id)
        )
