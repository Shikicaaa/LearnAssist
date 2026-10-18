import uuid

import pytest

from app.modules.artifacts.hashing import context_hash, normalize_topic, params_hash

BASE = dict(
    topic="aries",
    source_ids=[],
    num_questions=10,
    difficulty="hard",
    types=["mcq"],
    variant=0,
    script="latin",
)


@pytest.mark.parametrize(
    "variant",
    [
        "Sta je aries?",
        "Šta je ARIES????!?!????",
        "    šta       je aries??????",
        "Šta je aries...",
    ],
)
def test_normalize_topic(variant):
    assert normalize_topic(variant) == "sta je aries"


def test_inner_symbols_and_brackets_are_kept():
    assert normalize_topic("Sta je (aries)?") == "sta je (aries)"
    assert normalize_topic("Sta je [aries]?") == "sta je [aries]"
    assert normalize_topic("Sta je {aries}?") == "sta je {aries}"
    assert normalize_topic("Sta je <aries>?") == "sta je <aries>"
    assert normalize_topic("2+2") == "2+2"
    assert normalize_topic("2+2") != "2-2"
    assert normalize_topic("2 ? 2") == "2 ? 2"
    assert normalize_topic("sin(x)?") == "sin(x)"
    assert normalize_topic("sin(x)?") != "sin(x"
    assert normalize_topic("Café Münster") == "cafe munster"
    assert normalize_topic("Łódź") == "lodz"
    assert normalize_topic("Đak") == "djak"
    assert normalize_topic("Шта") != normalize_topic("Šta")


def test_params_hash_ignores_order_and_duplicates():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert params_hash(**{**BASE, "source_ids": [a, b]}) == params_hash(
        **{**BASE, "source_ids": [b, a]}
    )
    assert params_hash(**{**BASE, "source_ids": [a, b, b]}) == params_hash(
        **{**BASE, "source_ids": [b, a]}
    )
    assert params_hash(**{**BASE, "types": ["mcq", "tf"]}) == params_hash(
        **{**BASE, "types": ["tf", "mcq"]}
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("topic", "other"),
        ("num_questions", 5),
        ("difficulty", "medium"),
        ("types", ["tf"]),
        ("script", "cyrillic"),
        ("variant", 1),
    ],
)
def test_each_param_changes_the_hash(field, value):
    assert params_hash(**{**BASE, field: value}) != params_hash(**BASE)


def test_empty_topic_equals_no_topic():
    assert params_hash(**{**BASE, "topic": "???"}) == params_hash(**{**BASE, "topic": None})


def test_context_hash_keeps_chunk_boundaries():
    assert context_hash(["ab", "c"]) != context_hash(["a", "bc"])
    assert context_hash(["x", "y"]) == context_hash(["x", "y"])
