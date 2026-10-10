from app.modules.sources.parsers import SourceFormat

INGEST_TASK = "sources.ingest"

MIME_BY_FORMAT: dict[SourceFormat, str] = {
    SourceFormat.PDF: "application/pdf",
    SourceFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    SourceFormat.TXT: "text/plain",
    SourceFormat.MD: "text/markdown",
}
FORMAT_BY_MIME: dict[str, SourceFormat] = {mime: fmt for fmt, mime in MIME_BY_FORMAT.items()}
