import uuid
from collections.abc import Iterator
from typing import BinaryIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.modules.auth import UserOut, get_current_user
from app.modules.jobs import TaskQueue, get_task_queue
from app.modules.sessions import SessionOut, get_owned_session
from app.modules.sources.schemas import SourceOut, TextSourceCreate
from app.modules.sources.service import IncomingFile, SourcesService
from app.shared.db import get_db
from app.shared.storage import FileStorage, get_storage

router = APIRouter(tags=["sources"])
_CHUNK = 1024 * 1024


def get_sources_service(
    db: Session = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
    queue: TaskQueue = Depends(get_task_queue),
) -> SourcesService:
    return SourcesService(db, storage, queue)


@router.post("/sessions/{sid}/sources/files", response_model=list[SourceOut], status_code=202)
def upload_files(
    # Explicit "format: binary" so Swagger UI renders a file picker; the default OpenAPI 3.1
    # "contentMediaType" form is shown as plain text inputs by some Swagger UI versions.
    files: list[UploadFile] = File(
        ..., json_schema_extra={"items": {"type": "string", "format": "binary"}}
    ),
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    service: SourcesService = Depends(get_sources_service),
):
    uploads = [IncomingFile(f.filename or "file", f.file) for f in files]
    return service.add_files(user.id, session.id, uploads)


@router.post("/sessions/{sid}/sources/text", response_model=SourceOut, status_code=202)
def add_text(
    body: TextSourceCreate,
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    service: SourcesService = Depends(get_sources_service),
):
    return service.add_text(user.id, session.id, body.title, body.content)


@router.get("/sessions/{sid}/sources", response_model=list[SourceOut])
def list_sources(
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    service: SourcesService = Depends(get_sources_service),
):
    return service.list(user.id, session.id)


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(
    source_id: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    service: SourcesService = Depends(get_sources_service),
):
    return service.get(user.id, source_id)


def _stream(file: BinaryIO) -> Iterator[bytes]:
    with file:
        while block := file.read(_CHUNK):
            yield block


@router.get("/sources/{source_id}/file")
def download_original(
    source_id: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    service: SourcesService = Depends(get_sources_service),
):
    source, stream = service.open_original(user.id, source_id)
    filename = source.filename or f"{source.title}.txt"
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    media_type = source.mime or "application/octet-stream"
    if media_type.startswith("text/"):
        media_type += "; charset=utf-8"
    headers = {
        # "attachment" makes browsers download instead of rendering uploaded content in our origin.
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(filename)}",
        "Content-Length": str(source.size_bytes),
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(_stream(stream), media_type=media_type, headers=headers)


@router.post("/sources/{source_id}/reindex", response_model=SourceOut, status_code=202)
def reindex_source(
    source_id: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    service: SourcesService = Depends(get_sources_service),
):
    return service.reindex(user.id, source_id)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(
    source_id: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    service: SourcesService = Depends(get_sources_service),
) -> Response:
    service.delete(user.id, source_id)
    return Response(status_code=204)
