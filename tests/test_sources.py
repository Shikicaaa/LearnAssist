import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.embeddings import FakeEmbedder
from app.modules.sources.repository import SourceRepository
from app.shared.config import get_settings
from tests.files import (
    LOREM,
    docx_bytes,
    encrypt_pdf,
    make_docx,
    make_pdf,
    make_scanned_pdf,
)
from tests.helpers import (
    API,
    add_text,
    corpus_version,
    new_session,
    signup,
    sql,
    sql_one,
    stored_files,
    upload,
)

PDF = make_pdf([f"Page one. {LOREM}", f"Page two. {LOREM}", f"Page three. {LOREM}"]).getvalue()


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return signup(client, "bob@example.com")


@pytest.fixture
def sid(client, alice):
    return new_session(client, alice)


def chunk_count(source_id: str) -> int:
    return sql_one("SELECT count(*) FROM chunks WHERE source_id = :id", id=source_id)


class TestUpload:
    def test_pdf_becomes_ready_with_chunks_and_vectors(self, client, alice, sid):
        r = upload(client, alice, sid, ("lecture.pdf", PDF))
        assert r.status_code == 202
        [source] = r.json()
        assert source["status"] == "ready" and source["error"] is None
        assert source["type"] == "file" and source["title"] == "lecture.pdf"
        assert source["page_count"] == 3 and source["mime"] == "application/pdf"
        assert "storage_key" not in source and "content_hash" not in source

        rows = sql(
            "SELECT session_id::text, user_id::text, page_start, page_end, added_in_version,"
            " embedding_model, vector_dims(embedding) FROM chunks WHERE source_id = :id",
            id=source["id"],
        )
        assert rows
        for session_id, _user, page_start, page_end, version, model, dims in rows:
            assert session_id == sid
            assert 1 <= page_start <= page_end <= 3
            assert (version, model, dims) == (1, "multilingual-e5-small", 384)
        assert corpus_version(client, alice, sid) == 1

    def test_docx_txt_and_md_are_processed(self, client, alice, sid):
        docx = docx_bytes(make_docx(["Heading text.", LOREM])).getvalue()
        r = upload(
            client,
            alice,
            sid,
            ("notes.docx", docx),
            ("plain.txt", LOREM.encode()),
            ("readme.md", b"# Title\n\n" + LOREM.encode()),
        )
        assert r.status_code == 202
        sources = {s["title"]: s for s in r.json()}
        assert {s["status"] for s in sources.values()} == {"ready"}
        assert sources["notes.docx"]["page_count"] is None
        assert sources["readme.md"]["mime"] == "text/markdown"
        assert corpus_version(client, alice, sid) == 3

    def test_pasted_text_is_a_source(self, client, alice, sid):
        r = add_text(client, alice, sid, title="My notes", content=LOREM)
        assert r.status_code == 202
        body = r.json()
        assert body["type"] == "text" and body["filename"] is None
        assert body["status"] == "ready" and chunk_count(body["id"]) >= 1

    def test_swagger_gets_a_binary_file_field(self, client):
        spec = client.get("/openapi.json").json()
        schema = spec["components"]["schemas"][
            "Body_upload_files_api_v1_sessions__sid__sources_files_post"
        ]
        assert schema["properties"]["files"]["items"] == {"type": "string", "format": "binary"}

    def test_binary_body_instead_of_form_data_is_a_clear_422(self, client, alice, sid):
        r = client.post(
            f"{API}/sessions/{sid}/sources/files",
            content=PDF,
            headers={**alice, "Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 422

    def test_requires_authentication(self, client, sid):
        assert upload(client, {}, sid, ("a.txt", b"hello there")).status_code == 401
        assert add_text(client, {}, sid).status_code == 401

    def test_unsupported_file_is_415_and_nothing_is_stored(self, client, alice, sid):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        r = upload(client, alice, sid, ("photo.png", png))
        assert r.status_code == 415
        assert r.json()["error"]["code"] == "unsupported_media_type"
        assert sql_one("SELECT count(*) FROM sources") == 0 and stored_files() == []

    def test_empty_file_is_415(self, client, alice, sid):
        assert upload(client, alice, sid, ("empty.txt", b"")).status_code == 415

    def test_oversized_file_is_413_and_nothing_is_stored(self, client, alice, sid, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_file_size_mb", 0.001)
        r = upload(client, alice, sid, ("big.txt", b"x" * 2000))
        assert r.status_code == 413
        assert sql_one("SELECT count(*) FROM sources") == 0 and stored_files() == []

    def test_one_bad_file_rejects_the_whole_upload(self, client, alice, sid):
        r = upload(client, alice, sid, ("good.pdf", PDF), ("bad.png", b"\x89PNG\x00\x00\x00"))
        assert r.status_code == 415
        assert sql_one("SELECT count(*) FROM sources") == 0 and stored_files() == []

    def test_filename_is_cleaned_and_never_used_on_disk(self, client, alice, sid):
        r = upload(client, alice, sid, ("../../etc/passwd.txt", LOREM.encode()))
        assert r.json()[0]["title"] == "passwd.txt"
        [path] = stored_files()
        assert "passwd" not in str(path)
        uuid.UUID(path.name)  # stored under ids only

    def test_files_are_stored_per_user_and_session(self, client, alice, sid):
        upload(client, alice, sid, ("a.txt", LOREM.encode()))
        [path] = stored_files()
        user_id = client.get(f"{API}/auth/me", headers=alice).json()["id"]
        assert path.parent.parent.name == user_id and path.parent.name == sid


class TestDuplicatesAndLimits:
    def test_same_content_twice_in_a_session_is_409(self, client, alice, sid):
        upload(client, alice, sid, ("a.txt", LOREM.encode()))
        r = upload(client, alice, sid, ("renamed.txt", LOREM.encode()))
        assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
        assert len(stored_files()) == 1

    def test_same_file_twice_in_one_request_is_409(self, client, alice, sid):
        r = upload(client, alice, sid, ("a.txt", LOREM.encode()), ("b.txt", LOREM.encode()))
        assert r.status_code == 409
        assert sql_one("SELECT count(*) FROM sources") == 0

    def test_same_content_in_another_session_is_fine(self, client, alice, sid):
        other = new_session(client, alice, "Other")
        upload(client, alice, sid, ("a.txt", LOREM.encode()))
        assert upload(client, alice, other, ("a.txt", LOREM.encode())).status_code == 202

    def test_same_pasted_text_twice_is_409(self, client, alice, sid):
        add_text(client, alice, sid, content=LOREM)
        assert add_text(client, alice, sid, title="Again", content=LOREM).status_code == 409

    def test_content_can_be_added_again_after_deleting_the_source(self, client, alice, sid):
        first = upload(client, alice, sid, ("a.txt", LOREM.encode())).json()[0]
        client.delete(f"{API}/sources/{first['id']}", headers=alice)
        assert upload(client, alice, sid, ("a.txt", LOREM.encode())).status_code == 202

    def test_session_source_limit_is_429(self, client, alice, sid, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_sources_per_session", 2)
        for i in range(2):
            r = add_text(client, alice, sid, content=f"unique text number {i}")
            assert r.status_code == 202
        r = add_text(client, alice, sid, content="one too many")
        assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"

    def test_batch_over_the_limit_creates_nothing(self, client, alice, sid, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_sources_per_session", 2)
        files = [(f"f{i}.txt", f"different content {i}".encode()) for i in range(3)]
        assert upload(client, alice, sid, *files).status_code == 429
        assert sql_one("SELECT count(*) FROM sources") == 0 and stored_files() == []

    def test_deleted_sources_do_not_count_towards_the_limit(self, client, alice, sid, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_sources_per_session", 1)
        first = add_text(client, alice, sid, content="first").json()
        client.delete(f"{API}/sources/{first['id']}", headers=alice)
        assert add_text(client, alice, sid, content="second").status_code == 202

    def test_pasted_text_validation(self, client, alice, sid, monkeypatch):
        assert add_text(client, alice, sid, content="   \n ").status_code == 422
        assert add_text(client, alice, sid, title="  ").status_code == 422
        monkeypatch.setattr(get_settings(), "max_text_input_chars", 50)
        assert add_text(client, alice, sid, content="x" * 51).status_code == 413

    def test_concurrent_uploads_cannot_exceed_the_limit(self, client, alice, sid, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_sources_per_session", 3)
        real_count = SourceRepository.count_active

        def slow_count(self, session_id):
            # Widens the gap between "check the limit" and "insert", so that without the
            # advisory lock every thread would pass the check before any of them inserts.
            result = real_count(self, session_id)
            time.sleep(0.15)
            return result

        monkeypatch.setattr(SourceRepository, "count_active", slow_count)

        def attempt(i):
            return add_text(TestClient(app), alice, sid, content=f"distinct text {i}").status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(attempt, range(8)))
        assert statuses.count(202) == 3 and statuses.count(429) == 5

    def test_concurrent_identical_uploads_keep_only_one(self, client, alice, sid):
        def attempt(_):
            return add_text(TestClient(app), alice, sid, content="the very same text").status_code

        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(attempt, range(6)))
        assert statuses.count(202) == 1 and statuses.count(409) == 5
        assert len(stored_files()) == 1


class TestProcessingFailures:
    def test_scanned_pdf_fails_with_a_readable_message(self, client, alice, sid):
        [source] = upload(client, alice, sid, ("scan.pdf", make_scanned_pdf().getvalue())).json()
        assert source["status"] == "failed" and "scan" in source["error"]
        assert chunk_count(source["id"]) == 0 and corpus_version(client, alice, sid) == 0

    def test_password_protected_pdf_fails(self, client, alice, sid):
        locked = encrypt_pdf(make_pdf([LOREM]), "secret", "owner").getvalue()
        [source] = upload(client, alice, sid, ("locked.pdf", locked)).json()
        assert source["status"] == "failed" and "password" in source["error"]

    def test_corrupted_pdf_fails(self, client, alice, sid):
        [source] = upload(client, alice, sid, ("bad.pdf", b"%PDF-1.4\nnot really a pdf")).json()
        assert source["status"] == "failed" and "corrupted" in source["error"]

    def test_pdf_over_the_page_limit_fails(self, client, alice, sid, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_pdf_pages", 2)
        [source] = upload(client, alice, sid, ("long.pdf", PDF)).json()
        assert source["status"] == "failed" and "limit is 2" in source["error"]

    def test_a_failed_source_can_be_inspected_listed_and_deleted(self, client, alice, sid):
        [source] = upload(client, alice, sid, ("scan.pdf", make_scanned_pdf().getvalue())).json()
        assert client.get(f"{API}/sources/{source['id']}", headers=alice).json()["status"] == (
            "failed"
        )
        assert client.delete(f"{API}/sources/{source['id']}", headers=alice).status_code == 204


class TestReadingSources:
    def test_list_shows_only_own_non_deleted_sources_newest_first(self, client, alice, bob, sid):
        a = add_text(client, alice, sid, title="first", content="aaa one").json()
        add_text(client, alice, sid, title="second", content="bbb two")
        gone = add_text(client, alice, sid, title="gone", content="ccc three").json()
        client.delete(f"{API}/sources/{gone['id']}", headers=alice)
        listing = client.get(f"{API}/sessions/{sid}/sources", headers=alice).json()
        titles = [s["title"] for s in listing]
        assert titles == ["second", a["title"]]
        assert client.get(f"{API}/sessions/{sid}/sources", headers=bob).status_code == 404

    def test_get_one_source(self, client, alice, sid):
        created = add_text(client, alice, sid).json()
        r = client.get(f"{API}/sources/{created['id']}", headers=alice)
        assert r.status_code == 200 and r.json()["id"] == created["id"]

    def test_download_returns_the_original_bytes_as_an_attachment(self, client, alice, sid):
        source = upload(client, alice, sid, ("lecture.pdf", PDF)).json()[0]
        r = client.get(f"{API}/sources/{source['id']}/file", headers=alice)
        assert r.status_code == 200 and r.content == PDF
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("attachment;")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["content-length"] == str(len(PDF))

    def test_download_handles_non_ascii_filenames(self, client, alice, sid):
        name = "Ispitna pitanja čćšđž.txt"
        source = upload(client, alice, sid, (name, "Šta je đak?".encode())).json()[0]
        r = client.get(f"{API}/sources/{source['id']}/file", headers=alice)
        assert "UTF-8''Ispitna%20pitanja%20%C4%8D" in r.headers["content-disposition"]
        assert r.content.decode() == "Šta je đak?"
        assert r.headers["content-type"] == "text/plain; charset=utf-8"

    def test_pasted_text_downloads_as_txt(self, client, alice, sid):
        source = add_text(client, alice, sid, title="My notes", content="hello there").json()
        r = client.get(f"{API}/sources/{source['id']}/file", headers=alice)
        assert r.content == b"hello there"
        assert "My%20notes.txt" in r.headers["content-disposition"]


class TestIsolation:
    def test_other_users_cannot_touch_a_session_or_its_sources(self, client, alice, bob, sid):
        source = add_text(client, alice, sid).json()
        sid_url = f"{API}/sessions/{sid}/sources"
        src_url = f"{API}/sources/{source['id']}"
        responses = [
            upload(client, bob, sid, ("a.txt", b"hello there")),
            add_text(client, bob, sid),
            client.get(sid_url, headers=bob),
            client.get(src_url, headers=bob),
            client.get(f"{src_url}/file", headers=bob),
            client.post(f"{src_url}/reindex", headers=bob),
            client.delete(src_url, headers=bob),
        ]
        assert [r.status_code for r in responses] == [404] * 7
        assert client.get(src_url, headers=alice).status_code == 200

    def test_unknown_ids_look_the_same_as_foreign_ones(self, client, alice, bob, sid):
        source = add_text(client, alice, sid).json()
        foreign = client.get(f"{API}/sources/{source['id']}", headers=bob)
        missing = client.get(f"{API}/sources/{uuid.uuid4()}", headers=bob)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()

    def test_a_source_cannot_be_added_through_a_session_of_another_user(self, client, alice, bob):
        bobs_session = new_session(client, bob, "Bob's")
        add_text(client, alice, bobs_session)
        assert sql_one("SELECT count(*) FROM sources") == 0

    def test_vector_search_scoped_to_a_session_never_returns_foreign_chunks(
        self, client, alice, bob, sid
    ):
        add_text(client, alice, sid, content="photosynthesis converts light into chemical energy")
        bobs = new_session(client, bob, "Bob's")
        add_text(client, bob, bobs, content="photosynthesis converts light into chemical energy")
        vector = str(FakeEmbedder().embed_query("how does photosynthesis work"))
        rows = sql(
            "SELECT session_id::text FROM chunks WHERE session_id = :sid"
            " ORDER BY embedding <=> CAST(:q AS vector)",
            sid=sid,
            q=vector,
        )
        assert rows and {r[0] for r in rows} == {sid}


class TestSimilaritySearch:
    def test_nearest_chunk_is_the_relevant_one(self, client, alice, sid):
        add_text(client, alice, sid, title="bio", content="photosynthesis turns light into sugar")
        add_text(client, alice, sid, title="history", content="the battle was fought in 1389")
        vector = str(FakeEmbedder().embed_query("what does photosynthesis do with light"))
        [(text,)] = sql(
            "SELECT text FROM chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT 1", q=vector
        )
        assert "photosynthesis" in text


class TestReindex:
    def test_reindex_rebuilds_chunks_without_duplicates(self, client, alice, sid):
        source = upload(client, alice, sid, ("lecture.pdf", PDF)).json()[0]
        before = chunk_count(source["id"])
        r = client.post(f"{API}/sources/{source['id']}/reindex", headers=alice)
        assert r.status_code == 202 and r.json()["status"] == "ready"
        assert chunk_count(source["id"]) == before
        assert corpus_version(client, alice, sid) == 2
        versions = sql("SELECT DISTINCT added_in_version FROM chunks")
        assert [v[0] for v in versions] == [2]

    def test_reindex_of_a_failed_source_tries_again(self, client, alice, sid):
        source = upload(client, alice, sid, ("scan.pdf", make_scanned_pdf().getvalue())).json()[0]
        r = client.post(f"{API}/sources/{source['id']}/reindex", headers=alice)
        assert r.status_code == 202 and r.json()["status"] == "failed"

    @pytest.mark.parametrize("busy", ["queued", "processing"])
    def test_reindex_while_busy_is_409(self, client, alice, sid, busy):
        source = add_text(client, alice, sid).json()
        sql_update = "UPDATE sources SET status = :s WHERE id = :id"
        from sqlalchemy import text

        from app.shared.db import engine

        with engine.begin() as conn:
            conn.execute(text(sql_update), {"s": busy, "id": source["id"]})
        r = client.post(f"{API}/sources/{source['id']}/reindex", headers=alice)
        assert r.status_code == 409


class TestDelete:
    def test_delete_removes_chunks_file_and_bumps_the_version(self, client, alice, sid):
        source = upload(client, alice, sid, ("lecture.pdf", PDF)).json()[0]
        assert corpus_version(client, alice, sid) == 1 and len(stored_files()) == 1

        assert client.delete(f"{API}/sources/{source['id']}", headers=alice).status_code == 204

        assert client.get(f"{API}/sources/{source['id']}", headers=alice).status_code == 404
        assert chunk_count(source["id"]) == 0 and stored_files() == []
        assert corpus_version(client, alice, sid) == 2
        [(status, key)] = sql(
            "SELECT status, storage_key FROM sources WHERE id = :id", id=source["id"]
        )
        assert status == "deleted" and key is None

    def test_deleting_twice_is_404(self, client, alice, sid):
        source = add_text(client, alice, sid).json()
        client.delete(f"{API}/sources/{source['id']}", headers=alice)
        assert client.delete(f"{API}/sources/{source['id']}", headers=alice).status_code == 404

    def test_download_after_delete_is_404(self, client, alice, sid):
        source = add_text(client, alice, sid).json()
        client.delete(f"{API}/sources/{source['id']}", headers=alice)
        assert client.get(f"{API}/sources/{source['id']}/file", headers=alice).status_code == 404

    def test_deleting_a_session_removes_its_sources_chunks_and_files(self, client, alice, sid):
        upload(client, alice, sid, ("a.pdf", PDF), ("b.txt", LOREM.encode()))
        other = new_session(client, alice, "Keep me")
        add_text(client, alice, other, content="this one must survive")
        assert len(stored_files()) == 3

        assert client.delete(f"{API}/sessions/{sid}", headers=alice).status_code == 204

        assert sql_one("SELECT count(*) FROM sources") == 1
        assert sql_one("SELECT count(*) FROM chunks WHERE session_id = :s", s=sid) == 0
        [remaining] = stored_files()
        assert remaining.parent.name == other

    def test_a_missing_file_does_not_break_session_deletion(self, client, alice, sid):
        add_text(client, alice, sid)
        for path in stored_files():
            path.unlink()
        assert client.delete(f"{API}/sessions/{sid}", headers=alice).status_code == 204
