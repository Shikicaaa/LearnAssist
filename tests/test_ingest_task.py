import pytest
from sqlalchemy import text

from app.main import app
from app.modules.embeddings import FakeEmbedder
from app.modules.jobs import get_task_queue
from app.modules.sources import tasks
from app.shared.db import engine
from tests.files import LOREM, make_scanned_pdf
from tests.helpers import add_text, corpus_version, new_session, signup, sql, sql_one, stored_files


class RecordingQueue:
    """Accepts tasks without running them, so a test can run the task itself, on its own terms."""

    def __init__(self):
        self.sent = []

    def enqueue(self, name, payload):
        self.sent.append((name, payload))
        return "job-id"


@pytest.fixture
def headers(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def sid(client, headers):
    return new_session(client, headers)


@pytest.fixture
def queued(client, headers, sid):
    """A freshly uploaded source that is still `queued`: nothing has processed it yet."""
    app.dependency_overrides[get_task_queue] = RecordingQueue
    source = add_text(client, headers, sid, content=LOREM).json()
    assert source["status"] == "queued"
    return source["id"]


def run(source_id):
    return tasks.ingest_source.apply(kwargs={"source_id": source_id})


def status_and_error(source_id):
    [(status, error)] = sql("SELECT status, error FROM sources WHERE id = :id", id=source_id)
    return status, error


def chunks_of(source_id):
    return sql_one("SELECT count(*) FROM chunks WHERE source_id = :id", id=source_id)


def set_status(source_id, status):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sources SET status = :s WHERE id = :id"), {"s": status, "id": source_id}
        )


class FlakyEmbedder(FakeEmbedder):
    def __init__(self, error, failures):
        super().__init__()
        self.error, self.failures, self.calls = error, failures, 0

    def embed_passages(self, texts):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return super().embed_passages(texts)


class TestHappyPath:
    def test_queued_becomes_ready(self, queued):
        assert run(queued).state == "SUCCESS"
        assert status_and_error(queued) == ("ready", None)
        assert chunks_of(queued) >= 1

    def test_running_twice_does_not_duplicate_chunks(self, client, headers, sid, queued):
        run(queued)
        first = chunks_of(queued)
        run(queued)
        assert chunks_of(queued) == first
        assert corpus_version(client, headers, sid) == 2

    def test_unknown_source_is_ignored(self):
        assert run("00000000-0000-0000-0000-000000000000").state == "SUCCESS"

    def test_deleted_source_is_left_alone(self, queued):
        set_status(queued, "deleted")
        assert run(queued).state == "SUCCESS"
        assert status_and_error(queued)[0] == "deleted" and chunks_of(queued) == 0


class TestRetries:
    def test_temporary_errors_are_retried_until_it_works(self, monkeypatch, queued):
        embedder = FlakyEmbedder(ConnectionError("network down"), failures=2)
        monkeypatch.setattr(tasks, "get_embedder", lambda: embedder)
        assert run(queued).state == "SUCCESS"
        assert embedder.calls == 3
        assert status_and_error(queued) == ("ready", None)

    def test_gives_up_after_the_last_attempt_and_says_so(self, monkeypatch, queued):
        embedder = FlakyEmbedder(ConnectionError("network down"), failures=99)
        monkeypatch.setattr(tasks, "get_embedder", lambda: embedder)
        run(queued)
        assert embedder.calls == 6  # first attempt + 5 retries
        status, error = status_and_error(queued)
        assert status == "failed" and "several attempts" in error
        assert chunks_of(queued) == 0

    def test_unexpected_errors_fail_immediately_without_retrying(self, monkeypatch, queued):
        embedder = FlakyEmbedder(RuntimeError("bug"), failures=99)
        monkeypatch.setattr(tasks, "get_embedder", lambda: embedder)
        result = run(queued)
        assert embedder.calls == 1 and result.state == "FAILURE"
        status, error = status_and_error(queued)
        assert status == "failed" and "unexpectedly" in error


class TestPermanentFailures:
    def test_missing_original_file_fails_clearly(self, queued):
        for path in stored_files():
            path.unlink()
        run(queued)
        status, error = status_and_error(queued)
        assert status == "failed" and "no longer available" in error

    def test_failure_after_reindex_leaves_no_old_chunks_behind(self, queued):
        run(queued)
        assert chunks_of(queued) >= 1
        [path] = stored_files()
        path.write_bytes(make_scanned_pdf().getvalue())
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE sources SET mime = 'application/pdf' WHERE id = :id"), {"id": queued}
            )
        run(queued)
        status, error = status_and_error(queued)
        assert status == "failed" and "scan" in error
        assert chunks_of(queued) == 0

    def test_failure_does_not_change_the_corpus_version(self, client, headers, sid, queued):
        [path] = stored_files()
        path.write_bytes(b"%PDF-1.4\nthis is not a real pdf")
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE sources SET mime = 'application/pdf' WHERE id = :id"), {"id": queued}
            )
        run(queued)
        assert status_and_error(queued)[0] == "failed"
        assert corpus_version(client, headers, sid) == 0


class TestRacesWithUserActions:
    def test_source_deleted_while_processing_is_not_resurrected(
        self, client, headers, sid, queued, monkeypatch
    ):
        class DeletesDuringEmbedding(FakeEmbedder):
            def embed_passages(self, texts):
                set_status(queued, "deleted")
                return super().embed_passages(texts)

        monkeypatch.setattr(tasks, "get_embedder", lambda: DeletesDuringEmbedding())
        run(queued)
        assert status_and_error(queued)[0] == "deleted"
        assert chunks_of(queued) == 0 and corpus_version(client, headers, sid) == 0

    def test_result_is_dropped_if_the_source_was_requeued_meanwhile(
        self, client, headers, sid, queued, monkeypatch
    ):
        class RequeuesDuringEmbedding(FakeEmbedder):
            def embed_passages(self, texts):
                set_status(queued, "queued")
                return super().embed_passages(texts)

        monkeypatch.setattr(tasks, "get_embedder", lambda: RequeuesDuringEmbedding())
        run(queued)
        assert status_and_error(queued)[0] == "queued"
        assert chunks_of(queued) == 0 and corpus_version(client, headers, sid) == 0
