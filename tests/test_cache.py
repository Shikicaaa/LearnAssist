import pytest

from app.main import app
from app.modules import cache
from app.modules.cache import CacheContext
from app.modules.cache.normalize import meaning_markers, normalize_question
from app.modules.chat import service as chat_service
from app.modules.chat.followup import depends_on_history
from app.modules.chat.prompts import NO_ANSWER_MESSAGE, NO_SOURCES_MESSAGE
from app.modules.llm import FakeLLM, LLMUnavailableError, get_llm_provider
from app.shared.config import get_settings
from app.shared.db import SessionLocal
from tests.helpers import API, add_text, corpus_version, new_session, signup, sql, sql_one
from tests.test_chat import parse_sse

QUESTION = "what does photosynthesis convert"
ANSWER = "Fotosinteza pretvara svetlosnu energiju u hemijsku [1]."
# With top_k = 2 the weakest hit is "leaves" (one shared word), so a new chunk invalidates an
# answer only if it is closer to the question than that.
CLOSE = "what does photosynthesis convert light into energy"
MEDIUM = "photosynthesis happens in leaves"
FAR = "the battle of kosovo was fought in 1389"
NEW_RELEVANT = "photosynthesis convert energy what does"
# Words are chosen so the fake embedder (hash buckets) has no collision with the question.
NEW_IRRELEVANT = "integrals of polynomials"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "retrieval_min_score", 0.0)  # the fake embedder's scores are low
    monkeypatch.setattr(s, "retrieval_top_k", 2)
    return s


@pytest.fixture
def llm():
    fake = FakeLLM(reply=ANSWER)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_provider, None)


@pytest.fixture
def alice(client):
    return signup(client, "alice@example.com")


@pytest.fixture
def sid(client, alice):
    return new_session(client, alice)


@pytest.fixture
def filled(client, alice, sid):
    for title, content in (("close", CLOSE), ("medium", MEDIUM), ("far", FAR)):
        add_text(client, alice, sid, title=title, content=content)
    return sid


def ask(client, headers, sid, question=QUESTION, stream=False, **extra):
    url = f"{API}/sessions/{sid}/messages" + ("?stream=true" if stream else "")
    return client.post(url, json={"question": question, **extra}, headers=headers)


def entries(sid=None):
    if sid is None:
        return sql_one("SELECT count(*) FROM cache_entries")
    return sql_one("SELECT count(*) FROM cache_entries WHERE session_id = :s", s=sid)


class TestExactHit:
    def test_the_second_identical_question_does_not_call_the_model(
        self, client, alice, filled, llm
    ):
        first = ask(client, alice, filled).json()
        second = ask(client, alice, filled).json()
        assert len(llm.calls) == 1
        assert first["cached"] is False and second["cached"] is True
        assert second["content"] == first["content"] == ANSWER
        assert second["citations"] == first["citations"] != []

    def test_a_cached_answer_costs_nothing_and_says_where_it_came_from(
        self, client, alice, filled, llm
    ):
        ask(client, alice, filled)
        second = ask(client, alice, filled).json()
        assert (second["tokens_in"], second["tokens_out"]) == (0, 0)
        assert second["llm_provider"] is None and second["llm_model"] == "fake-model"
        [(entry_id,)] = sql("SELECT id FROM cache_entries")
        assert sql_one("SELECT cache_entry_id FROM messages WHERE cached") == entry_id

    def test_a_hit_is_stored_in_the_conversation_like_any_answer(self, client, alice, filled, llm):
        ask(client, alice, filled)
        ask(client, alice, filled)
        rows = sql("SELECT role, content, cached FROM messages ORDER BY created_at, role DESC")
        assert [(r, c) for r, c, _ in rows] == [("user", QUESTION), ("assistant", ANSWER)] * 2
        history = client.get(f"{API}/sessions/{filled}/messages", headers=alice).json()
        assert [m["cached"] for m in history["items"] if m["role"] == "assistant"] == [True, False]
        assert history["items"][0]["citations"][0]["source_title"] == "close"

    def test_hits_are_counted(self, client, alice, filled, llm):
        for _ in range(3):
            ask(client, alice, filled)
        assert sql_one("SELECT hit_count FROM cache_entries") == 2

    def test_case_spacing_diacritics_and_trailing_punctuation_do_not_matter(
        self, client, alice, filled, llm
    ):
        ask(client, alice, filled, "What does  PHOTOSYNTHESIS convert?")
        again = ask(client, alice, filled, "  what does photosynthesis convert ?! ").json()
        assert again["cached"] is True and len(llm.calls) == 1

    def test_streaming_a_hit_sends_the_same_events(self, client, alice, filled, llm):
        ask(client, alice, filled)
        events = parse_sse(ask(client, alice, filled, stream=True))
        assert [name for name, _ in events] == ["delta", "citations", "done"]
        assert events[0][1]["text"] == ANSWER
        assert events[2][1]["message"]["cached"] is True
        assert len(llm.calls) == 1

    def test_a_streamed_answer_is_cached_for_later(self, client, alice, filled, llm):
        ask(client, alice, filled, stream=True)
        assert ask(client, alice, filled).json()["cached"] is True
        assert len(llm.calls) == 1

    def test_a_no_answer_reply_is_cached_too(self, client, alice, filled, llm):
        llm.reply = "NEMA_ODGOVORA"
        ask(client, alice, filled, "who won the world cup")
        again = ask(client, alice, filled, "who won the world cup").json()
        assert again["cached"] is True and again["content"] == NO_ANSWER_MESSAGE
        assert again["citations"] == [] and len(llm.calls) == 1


class TestSimilarQuestions:
    def test_a_question_above_the_threshold_reuses_the_answer(
        self, client, alice, filled, llm, settings, monkeypatch
    ):
        monkeypatch.setattr(settings, "cache_similarity_threshold", 0.8)
        ask(client, alice, filled)
        near = ask(client, alice, filled, "what does photosynthesis convert exactly").json()
        assert near["cached"] is True and len(llm.calls) == 1

    def test_the_default_threshold_is_strict(self, client, alice, filled, llm):
        ask(client, alice, filled)
        near = ask(client, alice, filled, "what does photosynthesis convert exactly").json()
        assert near["cached"] is False and len(llm.calls) == 2

    def test_a_negated_question_is_not_the_same_question(
        self, client, alice, filled, llm, settings, monkeypatch
    ):
        # Embeddings barely see "not": the vectors are close, the answers are opposite.
        monkeypatch.setattr(settings, "cache_similarity_threshold", 0.8)
        ask(client, alice, filled)
        opposite = ask(client, alice, filled, "what does photosynthesis not convert").json()
        assert opposite["cached"] is False and len(llm.calls) == 2

    def test_a_question_with_other_numbers_is_not_the_same_question(
        self, client, alice, filled, llm, settings, monkeypatch
    ):
        monkeypatch.setattr(settings, "cache_similarity_threshold", 0.8)
        ask(client, alice, filled, "what does photosynthesis convert in 1389")
        other = ask(client, alice, filled, "what does photosynthesis convert in 1453").json()
        assert other["cached"] is False and len(llm.calls) == 2

    def test_the_closest_entry_may_be_rejected_in_favour_of_the_next(
        self, client, alice, filled, llm, settings, monkeypatch
    ):
        monkeypatch.setattr(settings, "cache_similarity_threshold", 0.8)
        ask(client, alice, filled)
        ask(client, alice, filled, "what does photosynthesis not convert exactly")
        # Worded closer to the negated entry (0.91) than to the plain one (0.89), but only the
        # plain one means the same.
        similar = ask(client, alice, filled, "what does photosynthesis convert exactly")
        assert similar.json()["cached"] is True and len(llm.calls) == 2
        hits = dict(sql("SELECT question_norm, hit_count FROM cache_entries"))
        assert hits == {
            "what does photosynthesis convert": 1,
            "what does photosynthesis not convert exactly": 0,
        }

    def test_an_unrelated_question_is_a_miss_even_with_a_loose_threshold(
        self, client, alice, filled, llm, settings, monkeypatch
    ):
        monkeypatch.setattr(settings, "cache_similarity_threshold", 0.5)
        ask(client, alice, filled)
        other = ask(client, alice, filled, "when was the battle of kosovo fought").json()
        assert other["cached"] is False and len(llm.calls) == 2


class TestNewMaterial:
    def test_a_new_chunk_closer_than_the_weakest_hit_invalidates_the_answer(
        self, client, alice, filled, llm
    ):
        ask(client, alice, filled)
        add_text(client, alice, filled, title="new", content=NEW_RELEVANT)
        again = ask(client, alice, filled).json()
        assert again["cached"] is False and len(llm.calls) == 2
        assert entries(filled) == 1  # the stale entry was replaced, not kept next to the new one

    def test_an_unrelated_new_chunk_keeps_the_answer_and_renews_its_version(
        self, client, alice, filled, llm
    ):
        ask(client, alice, filled)
        add_text(client, alice, filled, title="new", content=NEW_IRRELEVANT)
        assert ask(client, alice, filled).json()["cached"] is True
        assert len(llm.calls) == 1
        assert sql_one("SELECT corpus_version FROM cache_entries") == corpus_version(
            client, alice, filled
        )

    def test_a_renewed_entry_is_not_rechecked_against_old_chunks(self, client, alice, filled, llm):
        ask(client, alice, filled)
        add_text(client, alice, filled, title="new", content=NEW_IRRELEVANT)
        ask(client, alice, filled)
        add_text(client, alice, filled, title="newer", content=NEW_IRRELEVANT + " once more")
        assert ask(client, alice, filled).json()["cached"] is True

    def test_a_session_with_fewer_chunks_than_top_k_is_always_invalidated(
        self, client, alice, sid, llm
    ):
        # With fewer than k hits there is no "weakest hit", so any new chunk could have joined.
        add_text(client, alice, sid, title="only", content=CLOSE)
        ask(client, alice, sid)
        add_text(client, alice, sid, title="new", content=MEDIUM)  # even a weak match
        assert ask(client, alice, sid).json()["cached"] is False

    def test_deleting_a_cited_source_invalidates_the_answer(self, client, alice, sid, llm):
        first = add_text(client, alice, sid, title="close", content=CLOSE).json()
        add_text(client, alice, sid, title="medium", content=MEDIUM)
        add_text(client, alice, sid, title="far", content=FAR)
        cited = ask(client, alice, sid).json()["citations"][0]["source_id"]
        assert cited == first["id"]
        client.delete(f"{API}/sources/{first['id']}", headers=alice)
        assert sql_one("SELECT count(*) FROM cache_entry_citations") == 0  # CASCADE
        again = ask(client, alice, sid).json()
        assert again["cached"] is False and len(llm.calls) == 2

    def test_deleting_a_source_the_answer_did_not_use_keeps_it(self, client, alice, sid, llm):
        add_text(client, alice, sid, title="close", content=CLOSE)
        add_text(client, alice, sid, title="medium", content=MEDIUM)
        far = add_text(client, alice, sid, title="far", content=FAR).json()
        ask(client, alice, sid)
        client.delete(f"{API}/sources/{far['id']}", headers=alice)
        assert ask(client, alice, sid).json()["cached"] is True

    def test_reprocessing_a_cited_source_invalidates_the_answer(self, client, alice, sid, llm):
        first = add_text(client, alice, sid, title="close", content=CLOSE).json()
        add_text(client, alice, sid, title="medium", content=MEDIUM)
        add_text(client, alice, sid, title="far", content=FAR)
        ask(client, alice, sid)
        client.post(f"{API}/sources/{first['id']}/reindex", headers=alice)
        assert ask(client, alice, sid).json()["cached"] is False


class TestWhatAnAnswerDependsOn:
    def test_a_new_prompt_version_invalidates_everything(
        self, client, alice, filled, llm, monkeypatch
    ):
        ask(client, alice, filled)
        monkeypatch.setattr(chat_service, "prompt_version", lambda allow_general: "answer-v3")
        assert ask(client, alice, filled).json()["cached"] is False

    def test_another_model_does_not_get_the_old_models_answers(self, client, alice, filled, llm):
        ask(client, alice, filled)
        llm.model = "another-model"
        assert ask(client, alice, filled).json()["cached"] is False
        assert ask(client, alice, filled).json()["cached"] is True  # but then it has its own

    def test_a_different_top_k_does_not_share_answers(
        self, client, alice, filled, llm, settings, monkeypatch
    ):
        ask(client, alice, filled)
        monkeypatch.setattr(settings, "retrieval_top_k", 3)
        assert ask(client, alice, filled).json()["cached"] is False


class TestWhenTheCacheIsNotUsed:
    def test_a_session_can_switch_it_off(self, client, alice, filled, llm):
        client.patch(f"{API}/sessions/{filled}", json={"cache_enabled": False}, headers=alice)
        ask(client, alice, filled)
        assert ask(client, alice, filled).json()["cached"] is False
        assert len(llm.calls) == 2 and entries() == 0

    def test_switching_it_back_on_resumes_caching(self, client, alice, filled, llm):
        client.patch(f"{API}/sessions/{filled}", json={"cache_enabled": False}, headers=alice)
        ask(client, alice, filled)
        client.patch(f"{API}/sessions/{filled}", json={"cache_enabled": True}, headers=alice)
        ask(client, alice, filled)
        assert ask(client, alice, filled).json()["cached"] is True

    def test_a_request_can_skip_it(self, client, alice, filled, llm):
        ask(client, alice, filled)
        fresh = ask(client, alice, filled, use_cache=False).json()
        assert fresh["cached"] is False and len(llm.calls) == 2
        assert entries() == 1  # the earlier entry is untouched, and nothing new was stored

    def test_a_follow_up_that_leans_on_the_conversation_is_not_cached(
        self, client, alice, filled, llm
    ):
        ask(client, alice, filled)
        for _ in range(2):
            assert ask(client, alice, filled, "and what about that?").json()["cached"] is False
        assert len(llm.calls) == 3 and entries() == 1

    def test_a_first_question_is_stored_even_if_it_sounds_like_a_follow_up(
        self, client, alice, filled, llm
    ):
        # Nothing to lean on yet, so the question stands on its own...
        ask(client, alice, filled, "explain it again")
        assert entries() == 1
        # ...but once there is a conversation the same words may point back at it.
        assert ask(client, alice, filled, "explain it again").json()["cached"] is False

    def test_a_failed_model_call_stores_nothing(self, client, alice, filled, llm):
        llm.error = LLMUnavailableError("down")
        assert ask(client, alice, filled).status_code == 502
        assert entries() == 0

    def test_answers_without_a_model_are_not_stored(self, client, alice, sid, llm):
        assert ask(client, alice, sid).json()["content"] == NO_SOURCES_MESSAGE
        add_text(client, alice, sid, content=CLOSE)
        ask(client, alice, sid, "completely unrelated nonsense words")
        assert entries() == 1  # only the one the model answered

    def test_irrelevant_material_is_not_stored_either(
        self, client, alice, filled, llm, settings, monkeypatch
    ):
        monkeypatch.setattr(settings, "retrieval_min_score", 0.99)
        assert ask(client, alice, filled).json()["content"] == NO_ANSWER_MESSAGE
        assert entries() == 0

    def test_a_cache_failure_does_not_lose_the_answer(
        self, client, alice, filled, llm, monkeypatch
    ):
        def broken(*args, **kwargs):
            raise RuntimeError("cache is down")

        monkeypatch.setattr(chat_service.cache, "store", broken)
        body = ask(client, alice, filled)
        assert body.status_code == 200 and body.json()["content"] == ANSWER
        assert sql_one("SELECT count(*) FROM messages") == 2


class TestIsolation:
    def test_another_session_does_not_see_the_answer(self, client, alice, filled, llm):
        other = new_session(client, alice, "Other")
        for title, content in (("close", CLOSE), ("medium", MEDIUM), ("far", FAR)):
            add_text(client, alice, other, title=title, content=content)
        ask(client, alice, filled)
        assert ask(client, alice, other).json()["cached"] is False
        assert entries(filled) == 1 and entries(other) == 1

    def test_another_user_does_not_see_the_answer(self, client, alice, filled, llm):
        ask(client, alice, filled)
        bob = signup(client, "bob@example.com")
        bobs = new_session(client, bob)
        for title, content in (("close", CLOSE), ("medium", MEDIUM), ("far", FAR)):
            add_text(client, bob, bobs, title=title, content=content)
        assert ask(client, bob, bobs).json()["cached"] is False

    def test_deleting_the_session_deletes_its_cache(self, client, alice, filled, llm):
        ask(client, alice, filled)
        client.delete(f"{API}/sessions/{filled}", headers=alice)
        assert entries() == 0 and sql_one("SELECT count(*) FROM cache_entry_citations") == 0


class TestClearing:
    def test_clearing_forgets_the_answers_but_not_the_conversation(
        self, client, alice, filled, llm
    ):
        ask(client, alice, filled)
        assert client.post(f"{API}/sessions/{filled}/cache/clear", headers=alice).status_code == 204
        assert entries() == 0
        assert ask(client, alice, filled).json()["cached"] is False
        assert sql_one("SELECT count(*) FROM messages") == 4

    def test_clearing_keeps_the_cached_label_of_old_messages(self, client, alice, filled, llm):
        ask(client, alice, filled)
        ask(client, alice, filled)
        client.post(f"{API}/sessions/{filled}/cache/clear", headers=alice)
        assert sql_one("SELECT count(*) FROM messages WHERE cached") == 1
        assert sql_one("SELECT count(*) FROM messages WHERE cache_entry_id IS NOT NULL") == 0

    def test_only_the_owner_can_clear(self, client, alice, filled, llm):
        ask(client, alice, filled)
        bob = signup(client, "bob@example.com")
        r = client.post(f"{API}/sessions/{filled}/cache/clear", headers=bob)
        assert r.status_code == 404 and entries() == 1
        assert client.post(f"{API}/sessions/{filled}/cache/clear").status_code == 401

    def test_clearing_one_session_leaves_the_others(self, client, alice, filled, llm):
        other = new_session(client, alice, "Other")
        add_text(client, alice, other, content=CLOSE)
        ask(client, alice, filled)
        ask(client, alice, other)
        client.post(f"{API}/sessions/{filled}/cache/clear", headers=alice)
        assert entries(filled) == 0 and entries(other) == 1


class TestUnits:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("Šta je ARIES?", "sta  je aries"),
            ("Đak, i učitelj!", "djak, i ucitelj"),
            ("Why?", "why"),
        ],
    )
    def test_equivalent_questions_normalize_alike(self, a, b):
        assert normalize_question(a) == normalize_question(b)

    @pytest.mark.parametrize(
        ("a", "b"),
        [("2+3", "2-3"), ("3.14", "314"), ("x^2", "x^3"), ("integral of x+", "integral of x-")],
    )
    def test_symbols_keep_questions_apart(self, a, b):
        assert normalize_question(a) != normalize_question(b)

    @pytest.mark.parametrize(
        ("question", "markers"),
        [
            ("Šta je derivacija?", set()),
            ("Šta nije derivacija?", {"nije"}),
            ("Шта није извод", {"није"}),
            ("What is NOT a derivative", {"not"}),
            ("Don't explain it", {"dont"}),
            ("Koliko je 2+3 u 2024. godini", {"2+3", "2024"}),
            ("Zašto je x^2 veće od 10", {"x^2", "10"}),
        ],
    )
    def test_meaning_markers(self, question, markers):
        assert meaning_markers(normalize_question(question)) == markers

    @pytest.mark.parametrize(
        "question",
        [
            "a šta je sa tim?",
            "Objasni to detaljnije",
            "Ponovi još jednom",
            "what about that one",
            "and the second?",
            "Šta je prethodni primer?",
        ],
    )
    def test_follow_ups_are_recognized(self, question):
        assert depends_on_history(question)

    @pytest.mark.parametrize(
        "question",
        ["Šta je derivacija funkcije?", "Kada je bila bitka na Kosovu", "What does DNA encode", ""],
    )
    def test_standalone_questions_are_not(self, question):
        assert not depends_on_history(question)


class TestStoreAndLookupDirectly:
    """The parts of the key that the API cannot exercise on its own."""

    VECTOR = [1.0] + [0.0] * 383
    CONTEXT = CacheContext("multilingual-e5-small", "fake-model", "answer-v2", 2)

    def store(self, db, user_id, sid, *, question="Šta je đak", latin_only=True, answer="Latin"):
        cache.store(
            db,
            user_id=user_id,
            session_id=sid,
            corpus_version=0,
            question=question,
            vector=self.VECTOR,
            latin_only=latin_only,
            answer=answer,
            kth_score=0.0,
            context=self.CONTEXT,
            citations=[],
        )
        db.commit()

    def lookup(self, db, user_id, sid, *, question="Šta je đak", latin_only=True):
        return cache.lookup(
            db,
            user_id=user_id,
            session_id=sid,
            corpus_version=0,
            question=question,
            vector=self.VECTOR,
            latin_only=latin_only,
            context=self.CONTEXT,
        )

    def owner(self, sid):
        return sql_one("SELECT user_id FROM sessions WHERE id = :s", s=sid)

    def test_the_script_of_the_question_is_part_of_the_key(self, sid):
        # A Cyrillic question must not be given a Latin answer, however similar the vectors are.
        with SessionLocal() as db:
            self.store(db, self.owner(sid), sid)
            assert (
                self.lookup(db, self.owner(sid), sid, question="Шта је ђак", latin_only=False)
                is None
            )
            assert self.lookup(db, self.owner(sid), sid).answer == "Latin"

    def test_the_user_is_part_of_the_key(self, client, sid):
        bob = signup(client, "bob@example.com")
        bobs_id = sql_one("SELECT id FROM users WHERE email = 'bob@example.com'")
        del bob
        with SessionLocal() as db:
            self.store(db, self.owner(sid), sid)
            assert self.lookup(db, bobs_id, sid) is None

    def test_storing_the_same_question_again_replaces_the_entry(self, sid):
        with SessionLocal() as db:
            self.store(db, self.owner(sid), sid, answer="old")
            self.store(db, self.owner(sid), sid, answer="new")
            assert self.lookup(db, self.owner(sid), sid).answer == "new"
        assert entries(sid) == 1
