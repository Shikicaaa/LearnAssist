from app.modules.jobs import (
    InlineTaskQueue,
    PermanentError,
    TransientError,
    celery_app,
    task,
)

calls: dict[str, int] = {}


@task("test.flaky_then_ok")
def flaky_then_ok(fail_times: int):
    calls["flaky"] = calls.get("flaky", 0) + 1
    if calls["flaky"] <= fail_times:
        raise TransientError("baza privremeno nedostupna")
    return "ok"


@task("test.always_transient")
def always_transient():
    calls["transient"] = calls.get("transient", 0) + 1
    raise TransientError("uvek pada")


@task("test.permanent")
def permanent():
    calls["permanent"] = calls.get("permanent", 0) + 1
    raise PermanentError("pokvaren fajl")


def setup_function():
    calls.clear()


def run(name, **kwargs):
    return celery_app.tasks[name].apply(kwargs=kwargs)


def test_transient_error_is_retried_until_success():
    result = run("test.flaky_then_ok", fail_times=2)
    assert result.state == "SUCCESS" and result.get() == "ok"
    assert calls["flaky"] == 3


def test_transient_error_gives_up_after_max_retries():
    result = run("test.always_transient")
    assert result.state == "FAILURE"
    assert calls["transient"] == 6  # prvi pokušaj + 5 ponavljanja


def test_permanent_error_is_not_retried():
    result = run("test.permanent")
    assert result.state == "FAILURE"
    assert calls["permanent"] == 1


def test_inline_queue_runs_task_by_name():
    job_id = InlineTaskQueue().enqueue("test.flaky_then_ok", {"fail_times": 0})
    assert job_id and calls["flaky"] == 1
