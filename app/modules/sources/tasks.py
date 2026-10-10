import logging
import uuid

from sqlalchemy.exc import OperationalError

from app.modules.embeddings import get_embedder
from app.modules.jobs import PermanentError, TransientError, is_last_attempt, task
from app.modules.sessions import bump_corpus_version
from app.modules.sources.chunker import chunk_document
from app.modules.sources.constants import FORMAT_BY_MIME, INGEST_TASK
from app.modules.sources.events import publish_source_event
from app.modules.sources.models import Chunk, SourceStatus
from app.modules.sources.parsers import ParseError, parse_document
from app.modules.sources.repository import SourceRepository
from app.shared.config import get_settings
from app.shared.db import SessionLocal
from app.shared.storage import get_storage

logger = logging.getLogger(__name__)

# Errors worth retrying: the database or network may be back in a moment.
TRANSIENT_ERRORS = (TransientError, OperationalError, ConnectionError, TimeoutError)


@task(INGEST_TASK)
def ingest_source(source_id: str) -> None:
    try:
        _ingest(uuid.UUID(source_id))
    except PermanentError as exc:
        _fail(source_id, str(exc))
    except FileNotFoundError:
        _fail(source_id, "The original file is no longer available.")
    except TRANSIENT_ERRORS as exc:
        if is_last_attempt():
            logger.exception("Giving up on source %s after repeated failures", source_id)
            _fail(source_id, "Processing failed after several attempts. Try reindexing later.")
        else:
            raise TransientError(str(exc)) from exc
    except Exception:
        logger.exception("Unexpected error while ingesting source %s", source_id)
        _fail(source_id, "Processing failed unexpectedly.")
        raise


def _ingest(source_id: uuid.UUID) -> None:
    settings = get_settings()
    embedder = get_embedder()

    with SessionLocal() as db:
        repo = SourceRepository(db)
        source = repo.get_for_update(source_id)
        if source is None or source.status == SourceStatus.DELETED:
            return
        # Idempotency: whatever an earlier attempt left behind is removed before starting over.
        repo.delete_chunks(source_id)
        source.status = SourceStatus.PROCESSING.value
        source.error = None
        db.commit()
        publish_source_event(source)
        session_id, user_id = source.session_id, source.user_id
        storage_key, mime = source.storage_key, source.mime

    # The slow part runs without any open transaction or row lock.
    fmt = FORMAT_BY_MIME.get(mime or "")
    if fmt is None or storage_key is None:
        raise ParseError("The file type is not supported.")
    with get_storage().open(storage_key) as stream:
        document = parse_document(fmt, stream, settings.max_pdf_pages)
    chunks = chunk_document(
        document, embedder.count_tokens, settings.chunk_size, settings.chunk_overlap
    )
    if not chunks:
        raise ParseError("No text could be extracted from the file.")
    vectors = embedder.embed_passages([chunk.text for chunk in chunks])

    with SessionLocal() as db:
        repo = SourceRepository(db)
        source = repo.get_for_update(source_id)
        if source is None or source.status != SourceStatus.PROCESSING:
            # Deleted or re-queued while we were working: our result is stale, drop it.
            return
        # One transaction: chunks, status and corpus_version change together or not at all.
        version = bump_corpus_version(db, session_id)
        repo.add_chunks(
            [
                Chunk(
                    source_id=source_id,
                    session_id=session_id,
                    user_id=user_id,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    added_in_version=version,
                    embedding_model=embedder.model_name,
                    embedding=vector,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        source.status = SourceStatus.READY.value
        source.page_count = document.page_count
        db.commit()
        publish_source_event(source)


def _fail(source_id: str, message: str) -> None:
    with SessionLocal() as db:
        source = SourceRepository(db).mark_failed(uuid.UUID(source_id), message)
        db.commit()
        if source:
            publish_source_event(source)
