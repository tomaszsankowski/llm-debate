import asyncio
import json

import pytest

from app.groq_client import ProviderError
from app.models import Annotation
from app.simulation import Conflict, Engine, now
from app.storage import Storage
from tests.helpers import FakeProvider, config, finish


@pytest.fixture
def storage(tmp_path):
    store = Storage(str(tmp_path / "debates.sqlite3"))
    yield store
    store.close()


@pytest.mark.parametrize("first", ["A", "B", "random"])
async def test_turns_private_profiles_and_exact_requests(storage, first):
    provider = FakeProvider()
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=3, first_speaker=first))
    await finish(engine)
    result = storage.get(debate["id"])
    assert result["status"] == "completed"
    assert len(result["messages"]) == 6
    first_index = result["first_agent"]
    if first != "random":
        assert first_index == "AB".index(first)
    assert [message["agent_index"] for message in result["messages"]] == [
        (first_index + n) % 2 for n in range(6)
    ]
    assert [message["round"] for message in result["messages"]] == [1, 1, 2, 2, 3, 3]
    for n, request in enumerate(provider.requests):
        index = (first_index + n) % 2
        serialized = json.dumps(request)
        assert f"PRYWATNE_{'AB'[index]}" in serialized
        assert f"PRYWATNE_{'BA'[index]}" not in serialized
        assert "TAJNY_TEKST_ROZUMOWANIA" not in serialized
        assert len(request["messages"]) == n + 2
        assert request == result["attempts"][n]["request"]
        for message, original in zip(
            request["messages"][1:-1], result["messages"][:n], strict=True
        ):
            assert message["role"] == ("assistant" if original["agent_index"] == index else "user")
    assert "request" not in engine.view(debate["id"])["attempts"][0]


async def test_pause_finishes_current_turn_then_step_and_resume(storage):
    provider = FakeProvider(block=True)
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=2))
    await provider.started.wait()
    await engine.control(debate["id"], "pause")
    assert engine.get(debate["id"])["status"] == "pausing"
    provider.release.set()
    await finish(engine)
    assert len(engine.get(debate["id"])["messages"]) == 1
    assert engine.get(debate["id"])["status"] == "paused"
    await engine.control(debate["id"], "step")
    await finish(engine)
    assert len(engine.get(debate["id"])["messages"]) == 2
    assert engine.get(debate["id"])["status"] == "paused"
    await engine.control(debate["id"], "resume")
    await finish(engine)
    assert len(engine.get(debate["id"])["messages"]) == 4
    assert engine.get(debate["id"])["status"] == "completed"
    assert len(provider.requests) == 4
    with pytest.raises(Conflict):
        await engine.control(debate["id"], "resume")


async def test_stop_records_partial_without_public_turn(storage):
    provider = FakeProvider(block=True)
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=2))
    await provider.started.wait()
    await engine.control(debate["id"], "stop")
    result = storage.get(debate["id"])
    assert result["status"] == "stopped"
    assert result["messages"] == []
    assert result["attempts"][0]["status"] == "interrupted"
    assert result["attempts"][0]["content"] == "Publiczna wypowiedź."
    assert engine.active_id is None


async def test_stop_before_worker_starts_and_double_start(storage):
    engine = Engine(storage, FakeProvider(block=True))
    debate = await engine.create(config(rounds=1))
    with pytest.raises(Conflict):
        await engine.create(config(rounds=1))
    await engine.control(debate["id"], "stop")
    assert storage.get(debate["id"])["status"] == "stopped"
    assert engine.active_id is None


async def test_rate_limit_three_retries_then_manual_resume(storage):
    provider = FakeProvider([ProviderError("rate_limit", "Limit", 0) for _ in range(4)])
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=1))
    await finish(engine)
    result = engine.get(debate["id"])
    assert result["status"] == "error"
    assert len(result["attempts"]) == 4
    assert len(result["messages"]) == 0
    await engine.control(debate["id"], "resume")
    await finish(engine)
    result = storage.get(debate["id"])
    assert len(result["messages"]) == 2
    assert len(result["attempts"]) == 6
    assert result["attempts"][4]["number"] == 5
    assert result["attempts"][5]["number"] == 1


async def test_wait_can_be_paused_and_stopped_without_waiting(storage):
    engine = Engine(storage, FakeProvider([ProviderError("rate_limit", "Limit", 3600)]))
    debate = await engine.create(config(rounds=1))
    for _ in range(100):
        if engine.get(debate["id"])["status"] == "waiting":
            break
        await asyncio.sleep(0)
    assert engine.get(debate["id"])["status"] == "waiting"
    assert engine.get(debate["id"])["retry_at"]
    await engine.control(debate["id"], "pause")
    await finish(engine)
    assert engine.get(debate["id"])["status"] == "paused"
    assert engine.get(debate["id"])["retry_at"] is None


@pytest.mark.parametrize(
    "response",
    [
        {"content": "", "reasoning": "Tylko rozumowanie"},
        {"content": "Urwany tekst", "finish_reason": "length"},
        {"content": "Urwany strumień", "finish_reason": None},
    ],
)
async def test_incomplete_attempt_is_excluded_on_resume(storage, response):
    provider = FakeProvider([response])
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=1))
    await finish(engine)
    assert engine.get(debate["id"])["status"] == "error"
    assert engine.get(debate["id"])["messages"] == []
    await engine.control(debate["id"], "resume")
    await finish(engine)
    assert len(engine.get(debate["id"])["messages"]) == 2
    assert len(provider.requests[1]["messages"]) == 2


async def test_annotations_and_restart_preserve_transcript(tmp_path):
    path = str(tmp_path / "restart.sqlite3")
    storage = Storage(path)
    provider = FakeProvider(block=True)
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=1))
    await provider.started.wait()
    engine.annotate(debate["id"], Annotation(notes="Tylko dla badacza", outcome="partial"))
    await engine.close()
    storage.close()
    reopened = Storage(path)
    reopened.recover(now())
    result = reopened.get(debate["id"])
    assert result["status"] == "interrupted"
    assert result["annotations"]["notes"] == "Tylko dla badacza"
    assert result["attempts"][0]["content"]
    new_provider = FakeProvider()
    second = Engine(reopened, new_provider)
    await second.control(debate["id"], "resume")
    await finish(second)
    assert len(reopened.get(debate["id"])["messages"]) == 2
    assert "Tylko dla badacza" not in json.dumps(new_provider.requests)
    await second.close()
    reopened.close()


async def test_recover_after_unclean_exit(storage):
    engine = Engine(storage, FakeProvider(block=True))
    debate = await engine.create(config(rounds=1))
    await engine.provider.started.wait()
    engine.save(engine.get(debate["id"]))
    saved = storage.get(debate["id"])
    await engine.close()
    storage.save(saved)  # emulate process death before graceful shutdown was saved
    storage.recover(now())
    result = storage.get(debate["id"])
    assert result["status"] == "interrupted"
    assert result["attempts"][0]["status"] == "interrupted"
    assert result["attempts"][0]["content"]


async def test_concurrent_starts_and_event_subscriptions(storage):
    engine = Engine(storage, FakeProvider(block=True))
    results = await asyncio.gather(
        engine.create(config()), engine.create(config()), return_exceptions=True
    )
    assert sum(isinstance(result, Conflict) for result in results) == 1
    debate = next(result for result in results if isinstance(result, dict))
    queue = engine.subscribe(debate["id"])
    engine.annotate(debate["id"], Annotation(notes="x"))
    assert await queue.get()
    engine.unsubscribe(debate["id"], queue)
    assert debate["id"] not in engine.listeners
    await engine.control(debate["id"], "stop")


async def test_single_step_retries_rate_limit_then_pauses(storage):
    provider = FakeProvider(block=True)
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=2))
    await provider.started.wait()
    await engine.control(debate["id"], "pause")
    provider.release.set()
    await finish(engine)
    provider.responses = [ProviderError("rate_limit", "Limit", 0)]
    await engine.control(debate["id"], "step")
    await finish(engine)
    result = storage.get(debate["id"])
    assert result["status"] == "paused"
    assert len(result["messages"]) == 2
    assert len(result["attempts"]) == 3
