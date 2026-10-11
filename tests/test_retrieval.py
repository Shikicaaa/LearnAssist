import random
import uuid

import pytest
from sqlalchemy import event, text

from app.modules.embeddings import FakeEmbedder
from app.modules.retrieval import embed_question, get_chunk, retrieve
from app.shared.config import get_settings
from app.shared.db import SessionLocal, engine
from app.shared.errors import NotFoundError
from tests.helpers import add_text, new_session, signup, sql, sql_one

BIOLOGY = "photosynthesis converts light energy into chemical energy inside chloroplasts"
HISTORY = "the battle of kosovo was fought in 1389 between serbian and ottoman armies"
MATH = "the derivative measures the rate of change of a function at a point"

embedder = FakeEmbedder()


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return signup(client, "bob@example.com")


@pytest.fixture
def sid(client, alice):
    return new_session(client, alice)


def user_id(client, headers) -> uuid.UUID:
    return uuid.UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])


def search(client, headers, sid, question, **kwargs):
    with SessionLocal() as db:
        return retrieve(
            db,
            embedder=embedder,
            user_id=user_id(client, headers),
            session_id=uuid.UUID(sid),
            question_vector=embed_question(embedder, question),
            **kwargs,
        )


def fill(client, headers, sid):
    for title, content in (("bio", BIOLOGY), ("history", HISTORY), ("math", MATH)):
        add_text(client, headers, sid, title=title, content=content)


class TestSearch:
    def test_most_relevant_chunk_comes_first_and_scores_are_descending(self, client, alice, sid):
        fill(client, alice, sid)
        result = search(client, alice, sid, "what is photosynthesis", min_score=0.0)
        assert [c.source_title for c in result.chunks][0] == "bio"
        scores = [c.score for c in result.chunks]
        assert scores == sorted(scores, reverse=True)
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_top_k_limits_the_results(self, client, alice, sid):
        fill(client, alice, sid)
        assert len(search(client, alice, sid, "anything", top_k=2, min_score=0.0).chunks) == 2

    def test_chunks_carry_what_a_citation_needs(self, client, alice, sid):
        fill(client, alice, sid)
        chunk = search(client, alice, sid, "kosovo battle 1389", min_score=0.0).chunks[0]
        assert chunk.source_title == "history" and chunk.text == HISTORY
        assert chunk.page_start is None and chunk.page_end is None  # pasted text has no pages

    def test_empty_session_has_no_material(self, client, alice, sid):
        result = search(client, alice, sid, "anything")
        assert result.chunks == [] and result.has_material is False

    def test_min_score_drops_weak_matches_but_reports_material_exists(self, client, alice, sid):
        fill(client, alice, sid)
        result = search(client, alice, sid, "completely unrelated words here", min_score=0.99)
        assert result.chunks == [] and result.has_material is True

    def test_kth_score_is_zero_unless_the_top_k_is_full(self, client, alice, sid):
        fill(client, alice, sid)
        few = search(client, alice, sid, "photosynthesis", top_k=10, min_score=0.0)
        assert few.kth_score == 0.0
        full = search(client, alice, sid, "photosynthesis", top_k=3, min_score=0.0)
        assert full.kth_score == pytest.approx(full.chunks[-1].score)


class TestScoping:
    def test_other_users_and_other_sessions_are_never_searched(self, client, alice, bob, sid):
        add_text(client, alice, sid, title="mine", content=BIOLOGY)
        other = new_session(client, alice, "Other")
        add_text(client, alice, other, title="theirs", content=BIOLOGY)
        bobs = new_session(client, bob, "Bob's")
        add_text(client, bob, bobs, title="bobs", content=BIOLOGY)

        titles = {c.source_title for c in search(client, alice, sid, BIOLOGY, min_score=0.0).chunks}
        assert titles == {"mine"}

    def test_a_session_id_of_another_user_returns_nothing(self, client, alice, bob, sid):
        add_text(client, alice, sid, content=BIOLOGY)
        with SessionLocal() as db:
            result = retrieve(
                db,
                embedder=embedder,
                user_id=user_id(client, bob),  # bob asks about alice's session
                session_id=uuid.UUID(sid),
                question_vector=embed_question(embedder, BIOLOGY),
                min_score=0.0,
            )
        assert result.chunks == [] and result.has_material is False

    @pytest.mark.parametrize("status", ["queued", "processing", "failed", "deleted"])
    def test_only_ready_sources_are_searched(self, client, alice, sid, status):
        source = add_text(client, alice, sid, content=BIOLOGY).json()
        with SessionLocal() as db:
            db.execute(
                text("UPDATE sources SET status = :s WHERE id = :id"),
                {"s": status, "id": source["id"]},
            )
            db.commit()
        assert search(client, alice, sid, BIOLOGY, min_score=0.0).chunks == []

    def test_chunks_of_another_embedding_model_are_ignored(self, client, alice, sid):
        add_text(client, alice, sid, content=BIOLOGY)
        with SessionLocal() as db:
            db.execute(text("UPDATE chunks SET embedding_model = 'some-older-model'"))
            db.commit()
        assert search(client, alice, sid, BIOLOGY, min_score=0.0).chunks == []

    def test_deleted_sources_disappear_from_results(self, client, alice, sid):
        source = add_text(client, alice, sid, content=BIOLOGY).json()
        client.delete(f"/api/v1/sources/{source['id']}", headers=alice)
        assert search(client, alice, sid, BIOLOGY, min_score=0.0).chunks == []


class TestIndexedSearch:
    def test_session_still_gets_results_when_other_tenants_dominate_the_index(
        self, client, alice, bob, sid
    ):
        """Other users' chunks are *closer* to the question than mine. A plain HNSW scan returns
        the ~40 nearest chunks of everyone and only then filters, leaving my session empty;
        iterative scanning keeps going until it has found enough of my own."""
        fill(client, alice, sid)
        question = "photosynthesis converts light"
        alice_id = user_id(client, alice)

        bobs = new_session(client, bob, "Bob's")
        source = add_text(client, bob, bobs, title="bobs", content="seed").json()
        bob_id = sql_one("SELECT user_id::text FROM sources WHERE id = :id", id=source["id"])
        # 300 chunks of another user that are all very close to the question, but not identical:
        # identical vectors are a special case for the index and would not show the problem.
        rng = random.Random(1)
        base = embed_question(embedder, question)
        foreign = [
            {
                "src": source["id"],
                "sid": bobs,
                "uid": bob_id,
                "i": 100 + n,
                "vec": str([x + rng.gauss(0, 0.01) for x in base]),
            }
            for n in range(300)
        ]
        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO chunks (id, source_id, session_id, user_id, chunk_index, text,"
                    " char_start, char_end, added_in_version, embedding_model, embedding,"
                    " created_at, updated_at)"
                    " VALUES (gen_random_uuid(), :src, :sid, :uid, :i, 'filler', 0, 6, 1,"
                    " 'multilingual-e5-small', CAST(:vec AS vector), now(), now())"
                ),
                foreign,
            )
            db.execute(text("ANALYZE chunks"))
            db.commit()

            # Normally the planner does not use the HNSW index for this query at all: it prefers
            # the plain indexes and computes exact distances for the one session's rows. To test
            # the safety net for the day it does pick HNSW, remove the other ways in. DDL is
            # transactional in Postgres, so the rollback below restores everything.
            db.execute(text("DROP INDEX ix_chunks_session_id"))
            db.execute(text("ALTER TABLE chunks DROP CONSTRAINT uq_chunks_source_index"))
            db.execute(text("SET LOCAL enable_seqscan = off"))

            captured = []

            def capture(conn, cursor, statement, parameters, context, executemany):
                if "FROM chunks JOIN sources" in statement:
                    captured.append((statement, parameters))

            event.listen(engine, "before_cursor_execute", capture)
            try:
                result = retrieve(
                    db,
                    embedder=embedder,
                    user_id=alice_id,
                    session_id=uuid.UUID(sid),
                    question_vector=embed_question(embedder, question),
                    top_k=3,
                    min_score=0.0,
                )
            finally:
                event.remove(engine, "before_cursor_execute", capture)

            # Check the plan of the statement the application really ran, not of a lookalike.
            [(statement, parameters)] = captured
            plan = db.connection().exec_driver_sql("EXPLAIN " + statement, parameters)
            plan = "\n".join(row[0] for row in plan)
            assert "ix_chunks_embedding_hnsw" in plan, plan
            db.rollback()
        assert {c.source_title for c in result.chunks} == {"bio", "history", "math"}
        assert sql_one("SELECT count(*) FROM chunks WHERE text = 'filler'") == 300


class TestGetChunk:
    def test_returns_the_chunk_with_its_source(self, client, alice, sid):
        add_text(client, alice, sid, title="bio", content=BIOLOGY)
        [(chunk_id,)] = sql("SELECT id FROM chunks")
        with SessionLocal() as db:
            chunk = get_chunk(db, user_id=user_id(client, alice), chunk_id=chunk_id)
        assert (chunk.source_title, chunk.text, chunk.chunk_index) == ("bio", BIOLOGY, 0)

    def test_other_users_chunk_is_not_found(self, client, alice, bob, sid):
        add_text(client, alice, sid, content=BIOLOGY)
        [(chunk_id,)] = sql("SELECT id FROM chunks")
        with SessionLocal() as db, pytest.raises(NotFoundError):
            get_chunk(db, user_id=user_id(client, bob), chunk_id=chunk_id)

    def test_unknown_chunk_is_not_found(self, client, alice):
        with SessionLocal() as db, pytest.raises(NotFoundError):
            get_chunk(db, user_id=user_id(client, alice), chunk_id=uuid.uuid4())


def test_default_settings_are_sane():
    s = get_settings()
    assert s.retrieval_top_k >= 1 and 0.0 <= s.retrieval_min_score < 1.0
