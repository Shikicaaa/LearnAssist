import hashlib
import io
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.jobs import TaskQueue
from app.modules.sessions import bump_corpus_version
from app.modules.sources.constants import INGEST_TASK, MIME_BY_FORMAT
from app.modules.sources.models import Source, SourceStatus, SourceType
from app.modules.sources.parsers import SourceFormat, detect_format
from app.modules.sources.repository import SourceRepository
from app.shared.config import get_settings
from app.shared.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    QuotaExceededError,
    UnsupportedMediaTypeError,
)
from app.shared.storage import FileStorage, get_storage

logger = logging.getLogger(__name__)
_CHUNK = 1024 * 1024


@dataclass
class IncomingFile:
    filename: str
    data: BinaryIO


@dataclass
class _NewSource:
    id: uuid.UUID
    type: SourceType
    title: str
    filename: str | None
    mime: str
    size: int
    digest: str
    data: BinaryIO


def _clean_filename(raw: str | None) -> str:
    # Browsers may send a full path; keep only the last part and drop control characters.
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[-255:] or "file"


def _stream_size(data: BinaryIO) -> int:
    data.seek(0, io.SEEK_END)
    size = data.tell()
    data.seek(0)
    return size


def _sha256(data: BinaryIO) -> str:
    digest = hashlib.sha256()
    data.seek(0)
    while block := data.read(_CHUNK):
        digest.update(block)
    data.seek(0)
    return digest.hexdigest()


def _storage_key(user_id: uuid.UUID, session_id: uuid.UUID, source_id: uuid.UUID) -> str:
    # Built only from ids: the user-supplied filename never touches the file system.
    return f"{user_id}/{session_id}/{source_id}"


class SourcesService:
    def __init__(self, db: Session, storage: FileStorage, queue: TaskQueue):
        self.db = db
        self.storage = storage
        self.queue = queue
        self.repo = SourceRepository(db)

    def add_files(
        self, user_id: uuid.UUID, session_id: uuid.UUID, uploads: list[IncomingFile]
    ) -> list[Source]:
        settings = get_settings()
        max_bytes = int(settings.max_file_size_mb * 1024 * 1024)
        # Everything is validated before anything is stored: one bad file rejects the whole upload.
        items: list[_NewSource] = []
        seen: set[str] = set()
        for upload in uploads:
            name = _clean_filename(upload.filename)
            size = _stream_size(upload.data)
            if size > max_bytes:
                raise PayloadTooLargeError(
                    f"'{name}' is larger than the {settings.max_file_size_mb:g} MB limit"
                )
            fmt = detect_format(upload.data, name)
            if fmt is None:
                raise UnsupportedMediaTypeError(
                    f"'{name}' is empty or not a supported file (PDF, DOCX, TXT or MD)"
                )
            digest = _sha256(upload.data)
            if digest in seen:
                raise ConflictError(f"'{name}' appears more than once in this upload")
            seen.add(digest)
            items.append(
                _NewSource(
                    uuid.uuid4(),
                    SourceType.FILE,
                    name,
                    name,
                    MIME_BY_FORMAT[fmt],
                    size,
                    digest,
                    upload.data,
                )
            )
        return self._create(user_id, session_id, items)

    def add_text(
        self, user_id: uuid.UUID, session_id: uuid.UUID, title: str, content: str
    ) -> Source:
        limit = get_settings().max_text_input_chars
        if len(content) > limit:
            raise PayloadTooLargeError(f"The text is longer than {limit:,} characters")
        raw = content.encode("utf-8")
        item = _NewSource(
            uuid.uuid4(),
            SourceType.TEXT,
            title,
            None,
            MIME_BY_FORMAT[SourceFormat.TXT],
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            io.BytesIO(raw),
        )
        return self._create(user_id, session_id, [item])[0]

    def _create(
        self, user_id: uuid.UUID, session_id: uuid.UUID, items: list[_NewSource]
    ) -> list[Source]:
        limit = get_settings().max_sources_per_session
        saved: list[str] = []
        try:
            # Files go to disk first; if the database refuses them afterwards, they are removed.
            for item in items:
                key = _storage_key(user_id, session_id, item.id)
                item.data.seek(0)
                self.storage.save(key, item.data)
                saved.append(key)
            self.repo.lock_session_sources(session_id)
            if self.repo.count_active(session_id) + len(items) > limit:
                raise QuotaExceededError(f"A session can hold at most {limit} sources")
            existing = self.repo.active_hashes(session_id)
            for item in items:
                if item.digest in existing:
                    raise ConflictError(f"'{item.title}' has already been added to this session")
            rows = [
                self.repo.add(
                    id=item.id,
                    session_id=session_id,
                    user_id=user_id,
                    type=item.type.value,
                    title=item.title,
                    filename=item.filename,
                    mime=item.mime,
                    size_bytes=item.size,
                    storage_key=_storage_key(user_id, session_id, item.id),
                    content_hash=item.digest,
                    status=SourceStatus.QUEUED.value,
                )
                for item in items
            ]
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            self._discard(saved)
            raise ConflictError("One of the files has already been added to this session") from None
        except Exception:
            self.db.rollback()
            self._discard(saved)
            raise
        self._enqueue(rows)
        return rows

    def _enqueue(self, sources: list[Source]) -> None:
        # Only after the commit: a worker that starts early must find the row.
        for source in sources:
            try:
                self.queue.enqueue(INGEST_TASK, {"source_id": str(source.id)})
            except Exception:
                logger.exception("Could not enqueue source %s", source.id)
                self.repo.mark_failed(
                    source.id, "Processing could not be scheduled. Try reindexing."
                )
                self.db.commit()
            # The worker may already have changed the row (eager mode), so show the real state.
            self.db.refresh(source)

    def list(self, user_id: uuid.UUID, session_id: uuid.UUID) -> list[Source]:
        return self.repo.list_for_session(session_id, user_id)

    def get(self, user_id: uuid.UUID, source_id: uuid.UUID) -> Source:
        source = self.repo.get_owned(source_id, user_id)
        if source is None:
            raise NotFoundError("Source not found")
        return source

    def open_original(self, user_id: uuid.UUID, source_id: uuid.UUID) -> tuple[Source, BinaryIO]:
        source = self.get(user_id, source_id)
        try:
            return source, self.storage.open(source.storage_key or "")
        except (FileNotFoundError, ValueError):
            raise NotFoundError("The original file is no longer available") from None

    def reindex(self, user_id: uuid.UUID, source_id: uuid.UUID) -> Source:
        source = self.repo.get_owned(source_id, user_id, for_update=True)
        if source is None:
            raise NotFoundError("Source not found")
        if source.status not in (SourceStatus.READY, SourceStatus.FAILED):
            self.db.rollback()
            raise ConflictError("The source is still being processed")
        source.status = SourceStatus.QUEUED.value
        source.error = None
        self.db.commit()
        self._enqueue([source])
        return source

    def delete(self, user_id: uuid.UUID, source_id: uuid.UUID) -> None:
        source = self.repo.get_owned(source_id, user_id, for_update=True)
        if source is None:
            raise NotFoundError("Source not found")
        key = source.storage_key
        self.repo.delete_chunks(source.id)
        source.status = SourceStatus.DELETED.value
        source.error = None
        source.storage_key = None
        bump_corpus_version(self.db, source.session_id)
        self.db.commit()
        if key:
            self._discard([key])

    def _discard(self, keys: list[str]) -> None:
        for key in keys:
            try:
                self.storage.delete(key)
            except Exception:
                logger.exception("Could not delete stored file %s", key)


def collect_files_for_deletion(db: Session, session_id: uuid.UUID) -> Callable[[], None]:
    """Session delete hook: remembers the session's files and removes them after the commit."""
    keys = SourceRepository(db).storage_keys_for_session(session_id)
    storage = get_storage()

    def cleanup() -> None:
        for key in keys:
            try:
                storage.delete(key)
            except Exception:
                logger.exception("Could not delete stored file %s", key)

    return cleanup
