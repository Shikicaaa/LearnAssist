import json
import re
import threading
import time
import uuid

import pytest

from app.main import app
from app.modules import retrieval
from app.modules.artifacts import tasks
from app.modules.artifacts.constants import KIND_QUIZ, QUIZ_TASK
from app.modules.artifacts.repository import ArtifactKey, ArtifactRepository
from app.modules.embeddings import FakeEmbedder
from app.modules.jobs import InlineTaskQueue, get_task_queue
from app.modules.llm import FakeLLM, LLMEmptyResponseError, get_llm_provider
from app.shared.config import get_settings
from app.shared.db import SessionLocal
from tests.helpers import API, add_text, new_session, signup, sql, sql_one

BIOLOGY = "photosynthesis converts light energy into chemical energy inside chloroplasts"
HISTORY = "the battle of kosovo was fought in 1389 between serbian and ottoman armies"
MATH = "the derivative measures the rate of change of a function at a point"

embedder = FakeEmbedder()


def quiz_reply(count: int = 2) -> str:
    """A quiz whose quotes really are in BIOLOGY and HISTORY. Without a topic the sources are
    numbered in upload order, so rank 1 is the biology source and rank 2 the history one."""
    questions = [
        {
            "type": "mcq",
            "question": "What does photosynthesis convert?",
            "options": ["Light", "Sound", "Heat", "Wind"],
            "correct_index": 0,
            "correct_answer": None,
            "explanation": "The source says so.",
            "source_rank": 1,
            "evidence": "photosynthesis converts light energy into chemical energy",
        },
        {
            "type": "true_false",
            "question": "The battle of Kosovo was fought in 1389.",
            "options": ["True", "False"],
            "correct_index": 0,
            "correct_answer": None,
            "explanation": "The source says so.",
            "source_rank": 2,
            "evidence": "the battle of kosovo was fought in 1389",
        },
    ]
    return json.dumps({"questions": questions[:count]})


class RecordingQueue:
    """Remembers what was enqueued and runs nothing, so a test can decide when the worker runs."""

    def __init__(self):
        self.enqueued: list[tuple[str, dict]] = []

    def enqueue(self, name: str, payload: dict) -> str:
        self.enqueued.append((name, payload))
        return "task-id"


@pytest.fixture(autouse=True)
def lenient_settings(monkeypatch):
    # The fake embedder is a bag of words, so its similarities are far below a real model's.
    settings = get_settings()
    monkeypatch.setattr(settings, "retrieval_min_score", 0.0)
    monkeypatch.setattr(settings, "quiz_min_score", 0.0)
    monkeypatch.setattr(settings, "quiz_max_per_session", 50)
    monkeypatch.setattr(settings, "quiz_requests_per_hour", 100)
    monkeypatch.setattr(tasks, "get_embedder", lambda: embedder)


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM(reply=quiz_reply())
    app.dependency_overrides[get_llm_provider] = lambda: fake
    monkeypatch.setattr(tasks, "get_llm_provider", lambda: fake)
    yield fake
    app.dependency_overrides.pop(get_llm_provider, None)


@pytest.fixture
def queue():
    recorder = RecordingQueue()
    app.dependency_overrides[get_task_queue] = lambda: recorder
    yield recorder
    app.dependency_overrides[get_task_queue] = InlineTaskQueue


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return signup(client, "bob@example.com")


@pytest.fixture
def sid(client, alice):
    return new_session(client, alice)


@pytest.fixture
def filled(client, alice, sid):
    for title, content in (("bio", BIOLOGY), ("history", HISTORY), ("math", MATH)):
        add_text(client, alice, sid, title=title, content=content)
    return sid


def post_quiz(client, headers, sid, **body):
    body.setdefault("types", ["mcq", "true_false"])  # what quiz_reply() contains
    return client.post(f"{API}/sessions/{sid}/quizzes", json=body, headers=headers)


def source_id(client, headers, sid, title: str) -> str:
    items = client.get(f"{API}/sessions/{sid}/sources", headers=headers).json()
    return next(item["id"] for item in items if item["title"] == title)


def user_id(client, headers) -> uuid.UUID:
    return uuid.UUID(client.get(f"{API}/auth/me", headers=headers).json()["id"])


class TestCreating:
    def test_a_quiz_is_generated_from_the_material(self, client, alice, filled, llm):
        response = post_quiz(client, alice, filled)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        first, second = body["content"]["questions"]
        assert (first["type"], second["type"]) == ("mcq", "true_false")
        assert first["correct_index"] == 0
        assert first["citation"]["source_title"] == "bio"
        assert second["citation"]["source_title"] == "history"
        assert body["tokens_in"] == 7 and body["tokens_out"] == 11
        assert body["llm_model"] == "fake-model"

    def test_the_model_is_given_the_sources_and_a_generous_output_limit(
        self, client, alice, filled, llm
    ):
        post_quiz(client, alice, filled)

        (call,) = llm.calls
        assert "IZVORI:" in call["messages"][0].content
        assert "photosynthesis" in call["messages"][0].content
        assert call["max_output_tokens"] == get_settings().quiz_max_output_tokens
        assert "NEMA_MATERIJALA" in call["system"]

    def test_a_topic_narrows_the_material(self, client, alice, filled, llm):
        response = post_quiz(client, alice, filled, topic="photosynthesis")

        assert response.json()["status"] == "ready"
        assert response.json()["params"]["topic"] == "photosynthesis"

    def test_no_sources_means_no_quiz(self, client, alice, sid, llm):
        response = post_quiz(client, alice, sid)

        assert response.status_code == 400
        assert "no material" in response.json()["error"]["message"]
        assert llm.calls == []

    def test_too_many_questions_are_refused(self, client, alice, filled, llm):
        response = post_quiz(client, alice, filled, num_questions=26)

        assert response.status_code == 400
        assert llm.calls == []

    def test_a_bad_request_is_a_validation_error(self, client, alice, filled, llm):
        assert post_quiz(client, alice, filled, difficulty="impossible").status_code == 422
        assert post_quiz(client, alice, filled, types=[]).status_code == 422


class TestCaching:
    def test_the_same_request_is_served_from_the_store(self, client, alice, filled, llm):
        first = post_quiz(client, alice, filled).json()
        second = post_quiz(client, alice, filled)

        assert second.status_code == 200
        assert second.json()["id"] == first["id"]
        assert len(llm.calls) == 1

    def test_a_differently_spelled_topic_is_the_same_request(self, client, alice, filled, llm):
        first = post_quiz(client, alice, filled, topic="Photosynthesis?").json()
        second = post_quiz(client, alice, filled, topic="  photosynthesis ").json()

        assert second["id"] == first["id"]
        assert len(llm.calls) == 1

    def test_the_order_of_sources_and_types_does_not_matter(self, client, alice, filled, llm):
        bio = source_id(client, alice, filled, "bio")
        history = source_id(client, alice, filled, "history")
        first = post_quiz(
            client, alice, filled, source_ids=[bio, history], types=["mcq", "true_false"]
        )
        second = post_quiz(
            client, alice, filled, source_ids=[history, bio], types=["true_false", "mcq"]
        )

        assert first.json()["status"] == "ready"
        assert second.json()["id"] == first.json()["id"]
        assert len(llm.calls) == 1

    @pytest.mark.parametrize(
        "change",
        [{"difficulty": "hard"}, {"num_questions": 3}, {"types": ["true_false"]}, {"topic": "x"}],
        ids=["difficulty", "size", "types", "topic"],
    )
    def test_another_request_is_another_quiz(self, client, alice, filled, llm, change):
        first = post_quiz(client, alice, filled).json()
        second = post_quiz(client, alice, filled, **change).json()

        assert second["id"] != first["id"]
        assert len(llm.calls) == 2

    def test_new_material_makes_a_new_quiz(self, client, alice, filled, llm):
        first = post_quiz(client, alice, filled).json()
        add_text(client, alice, filled, title="chemistry", content="water is made of hydrogen")
        second = post_quiz(client, alice, filled).json()

        assert second["id"] != first["id"]
        assert len(llm.calls) == 2

    def test_regenerate_gives_a_new_variant_and_plain_requests_keep_the_first(
        self, client, alice, filled, llm
    ):
        first = post_quiz(client, alice, filled).json()
        again = post_quiz(client, alice, filled, regenerate=True).json()
        third = post_quiz(client, alice, filled, regenerate=True).json()
        plain = post_quiz(client, alice, filled).json()

        assert len({first["id"], again["id"], third["id"]}) == 3
        assert plain["id"] == first["id"]
        variants = sql("SELECT variant FROM artifacts ORDER BY variant")
        assert [row.variant for row in variants] == [0, 1, 2]
        assert len(llm.calls) == 3


class TestLimits:
    def test_the_rate_limit_applies_to_the_model_but_not_to_the_store(
        self, client, alice, filled, llm, monkeypatch
    ):
        monkeypatch.setattr(get_settings(), "quiz_requests_per_hour", 1)

        assert post_quiz(client, alice, filled).status_code == 200
        assert post_quiz(client, alice, filled, difficulty="hard").status_code == 429
        assert post_quiz(client, alice, filled).status_code == 200  # stored: costs nothing
        assert len(llm.calls) == 1

    def test_a_session_holds_a_limited_number_of_quizzes(
        self, client, alice, filled, llm, monkeypatch
    ):
        monkeypatch.setattr(get_settings(), "quiz_max_per_session", 1)
        first = post_quiz(client, alice, filled).json()

        refused = post_quiz(client, alice, filled, difficulty="hard")
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "quota_exceeded"

        client.delete(f"{API}/artifacts/{first['id']}", headers=alice)
        assert post_quiz(client, alice, filled, difficulty="hard").status_code == 200


class TestFailures:
    def test_an_unusable_reply_fails_the_quiz_and_the_same_request_can_be_retried(
        self, client, alice, filled, llm
    ):
        llm.reply = "Sorry, I cannot do that."
        failed = post_quiz(client, alice, filled)

        assert failed.status_code == 200
        assert failed.json()["status"] == "failed"
        assert "usable quiz" in failed.json()["error"]
        assert len(llm.calls) == 2  # the first reply, then one more try

        llm.reply = quiz_reply()
        retried = post_quiz(client, alice, filled).json()
        assert retried["id"] == failed.json()["id"]
        assert retried["status"] == "ready"
        assert retried["error"] is None

    def test_a_failed_quiz_does_not_use_up_the_session_quota(
        self, client, alice, filled, llm, monkeypatch
    ):
        monkeypatch.setattr(get_settings(), "quiz_max_per_session", 1)
        llm.reply = "nope"
        assert post_quiz(client, alice, filled).json()["status"] == "failed"

        llm.reply = quiz_reply()
        assert post_quiz(client, alice, filled, difficulty="hard").json()["status"] == "ready"

    def test_not_enough_material_is_reported(self, client, alice, filled, llm):
        llm.reply = "NEMA_MATERIJALA"
        body = post_quiz(client, alice, filled).json()

        assert body["status"] == "failed"
        assert "does not contain enough" in body["error"]
        assert len(llm.calls) == 1  # no point asking again

    def test_a_permanent_model_error_fails_the_quiz(self, client, alice, filled, llm):
        llm.error = LLMEmptyResponseError("The model returned nothing.")
        body = post_quiz(client, alice, filled).json()

        assert body["status"] == "failed"
        assert body["error"] == "The model returned nothing."


class TestAsynchronously:
    """With a real queue the request returns at once and a worker finishes the quiz later."""

    def test_pending_then_ready(self, client, alice, filled, llm, queue):
        response = post_quiz(client, alice, filled)
        assert response.status_code == 202
        pending = response.json()
        assert pending["status"] == "pending" and pending["content"] is None
        assert queue.enqueued == [(QUIZ_TASK, {"artifact_id": pending["id"]})]

        tasks.generate_quiz_task(pending["id"])  # what the worker does

        ready = client.get(f"{API}/artifacts/{pending['id']}", headers=alice).json()
        assert ready["status"] == "ready" and len(ready["content"]["questions"]) == 2
        assert post_quiz(client, alice, filled).status_code == 200

    def test_asking_again_while_it_is_pending_does_not_start_a_second_job(
        self, client, alice, filled, llm, queue
    ):
        first = post_quiz(client, alice, filled).json()
        second = post_quiz(client, alice, filled)

        assert second.status_code == 202
        assert second.json()["id"] == first["id"]
        assert len(queue.enqueued) == 1

    def test_an_abandoned_pending_quiz_is_started_again(self, client, alice, filled, llm, queue):
        first = post_quiz(client, alice, filled).json()
        sql("SELECT 1")  # (keeps the helper import honest)
        from app.shared.db import engine

        with engine.begin() as conn:
            conn.exec_driver_sql("UPDATE artifacts SET updated_at = now() - interval '2 hours'")

        again = post_quiz(client, alice, filled).json()
        assert again["id"] == first["id"]
        assert len(queue.enqueued) == 2

    def test_the_worker_is_idempotent(self, client, alice, filled, llm, queue):
        pending = post_quiz(client, alice, filled).json()
        tasks.generate_quiz_task(pending["id"])
        tasks.generate_quiz_task(pending["id"])  # redelivered

        assert len(llm.calls) == 1

    def test_material_that_changed_while_waiting_fails_the_quiz(
        self, client, alice, filled, llm, queue
    ):
        pending = post_quiz(client, alice, filled).json()
        add_text(client, alice, filled, title="chemistry", content="water is made of hydrogen")
        for name, payload in queue.enqueued[1:]:  # the recording queue only noted the ingestion
            InlineTaskQueue().enqueue(name, payload)

        tasks.generate_quiz_task(pending["id"])

        body = client.get(f"{API}/artifacts/{pending['id']}", headers=alice).json()
        assert body["status"] == "failed"
        assert "material changed" in body["error"]
        assert llm.calls == []

    def test_a_deleted_quiz_is_skipped_by_the_worker(self, client, alice, filled, llm, queue):
        pending = post_quiz(client, alice, filled).json()
        client.delete(f"{API}/artifacts/{pending['id']}", headers=alice)

        tasks.generate_quiz_task(pending["id"])

        assert llm.calls == []


class TestAccess:
    def test_quizzes_are_private(self, client, alice, bob, filled, llm):
        quiz = post_quiz(client, alice, filled).json()

        assert client.get(f"{API}/artifacts/{quiz['id']}", headers=bob).status_code == 404
        assert client.delete(f"{API}/artifacts/{quiz['id']}", headers=bob).status_code == 404
        assert post_quiz(client, bob, filled).status_code == 404
        assert client.get(f"{API}/sessions/{filled}/artifacts", headers=bob).status_code == 404

    def test_authentication_is_required(self, client, filled):
        assert client.post(f"{API}/sessions/{filled}/quizzes", json={}).status_code == 401
        assert client.get(f"{API}/artifacts/{uuid.uuid4()}").status_code == 401

    def test_list_newest_first(self, client, alice, filled, llm):
        first = post_quiz(client, alice, filled).json()
        second = post_quiz(client, alice, filled, difficulty="hard").json()

        page = client.get(f"{API}/sessions/{filled}/artifacts", headers=alice).json()
        assert page["total"] == 2
        assert [item["id"] for item in page["items"]] == [second["id"], first["id"]]

    def test_delete(self, client, alice, filled, llm):
        quiz = post_quiz(client, alice, filled).json()

        assert client.delete(f"{API}/artifacts/{quiz['id']}", headers=alice).status_code == 204
        assert client.get(f"{API}/artifacts/{quiz['id']}", headers=alice).status_code == 404
        assert client.delete(f"{API}/artifacts/{quiz['id']}", headers=alice).status_code == 404

    def test_deleting_the_session_deletes_its_quizzes(self, client, alice, filled, llm):
        post_quiz(client, alice, filled)
        assert sql_one("SELECT count(*) FROM artifacts") == 1

        client.delete(f"{API}/sessions/{filled}", headers=alice)

        assert sql_one("SELECT count(*) FROM artifacts") == 0


class TestClaim:
    def key(self, sid: str) -> ArtifactKey:
        return ArtifactKey(uuid.UUID(sid), KIND_QUIZ, "p" * 64, "c" * 64, "quiz-test", "model")

    def test_the_second_claim_gets_the_first_row(self, client, alice, sid):
        uid = user_id(client, alice)
        with SessionLocal() as db:
            repo = ArtifactRepository(db)
            first, created_first = repo.claim(self.key(sid), variant=0, user_id=uid, params={})
            db.commit()
            second, created_second = repo.claim(self.key(sid), variant=0, user_id=uid, params={})

        assert (created_first, created_second) == (True, False)
        assert first.id == second.id
        assert first.status == "pending"

    def test_variants_are_separate_rows(self, client, alice, sid):
        uid = user_id(client, alice)
        with SessionLocal() as db:
            repo = ArtifactRepository(db)
            repo.claim(self.key(sid), variant=0, user_id=uid, params={})
            _, created = repo.claim(self.key(sid), variant=1, user_id=uid, params={})
            assert created
            assert repo.next_variant(self.key(sid)) == 2

    def test_simultaneous_claims_create_exactly_one_row(self, client, alice, sid):
        uid = user_id(client, alice)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        def claim():
            with SessionLocal() as db:
                barrier.wait()
                _, created = ArtifactRepository(db).claim(
                    self.key(sid), variant=0, user_id=uid, params={}
                )
                if created:
                    time.sleep(0.3)  # keep the row uncommitted while the other one tries
                db.commit()
                results.append(created)

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(results) == [False, True]
        assert sql_one("SELECT count(*) FROM artifacts") == 1


class TestSampling:
    """`retrieval.sample_material`: what a quiz without a topic is built from."""

    @pytest.fixture(autouse=True)
    def small_chunks(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "chunk_size", 12)
        monkeypatch.setattr(get_settings(), "chunk_overlap", 2)

    @pytest.fixture
    def long_sources(self, client, alice, sid):
        for title, prefix, words in (("a", "alpha", 100), ("b", "beta", 100), ("c", "gamma", 30)):
            text = " ".join(f"{prefix}{i}" for i in range(words))
            add_text(client, alice, sid, title=title, content=text)
        assert sql_one("SELECT count(*) FROM chunks") > 12
        return sid

    def sample(self, client, headers, sid, limit, ids=()):
        with SessionLocal() as db:
            return retrieval.sample_material(
                db,
                user_id=user_id(client, headers),
                session_id=uuid.UUID(sid),
                embedding_model=embedder.model_name,
                source_ids=[uuid.UUID(i) for i in ids],
                limit=limit,
            )

    def test_never_more_than_the_limit_and_every_source_is_present(
        self, client, alice, long_sources
    ):
        chunks = self.sample(client, alice, long_sources, limit=9)

        assert 0 < len(chunks) <= 9
        assert {c.source_title for c in chunks} == {"a", "b", "c"}

    def test_the_same_material_gives_the_same_sample(self, client, alice, long_sources):
        first = self.sample(client, alice, long_sources, limit=9)
        second = self.sample(client, alice, long_sources, limit=9)

        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]

    def test_the_sample_is_spread_over_the_whole_source(self, client, alice, long_sources):
        chunks = self.sample(client, alice, long_sources, limit=9)
        words = [
            int(n)
            for c in chunks
            if c.source_title == "a"
            for n in re.findall(r"alpha(\d+)", c.text)
        ]

        assert min(words) < 30  # the beginning of the source is in the sample...
        assert max(words) > 70  # ...and so is the end

    def test_only_the_chosen_sources_are_used(self, client, alice, long_sources):
        by_title = {row.title: str(row.id) for row in sql("SELECT id, title FROM sources")}
        chunks = self.sample(client, alice, long_sources, limit=9, ids=[by_title["b"]])

        assert {c.source_title for c in chunks} == {"b"}

    def test_a_limit_below_the_number_of_sources_is_still_respected(
        self, client, alice, long_sources
    ):
        assert len(self.sample(client, alice, long_sources, limit=2)) <= 2

    def test_someone_elses_session_gives_nothing(self, client, alice, bob, long_sources):
        assert self.sample(client, bob, long_sources, limit=9) == []
