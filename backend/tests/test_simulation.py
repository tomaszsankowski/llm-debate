import asyncio
import json

import pytest

from app import simulation
from app.gemini_client import GeminiError
from app.models import Annotation
from app.simulation import Conflict, Engine, now
from app.storage import Storage
from tests.helpers import FakeGemini, config, finish


@pytest.fixture
def storage(tmp_path):
    store = Storage(str(tmp_path / "debates.sqlite3"))
    yield store
    store.close()


@pytest.mark.parametrize("first", ["A", "B", "random"])
async def test_turns_private_profiles_and_exact_requests(storage, first):
    provider = FakeGemini()
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
        assert request == result["attempts"][n]["request"]
        native_messages = [
            (item["role"], part["text"])
            for item in request["contents"]
            for part in item["parts"]
            if part["text"].startswith("[")
        ]
        assert len(native_messages) == n
        for (role, content), original in zip(native_messages, result["messages"][:n], strict=True):
            assert role == ("model" if original["agent_index"] == index else "user")
            assert content.endswith(original["content"])
    assert "request" not in engine.view(debate["id"])["attempts"][0]


async def test_pause_finishes_current_turn_then_step_and_resume(storage):
    provider = FakeGemini(block=True)
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
    provider = FakeGemini(block=True)
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


async def test_saved_model_is_preserved_on_resume_and_client_is_closed(storage):
    client = FakeGemini(block=True)
    engine = Engine(storage, client)
    debate = await engine.create(config(rounds=2))
    await client.started.wait()
    await engine.control(debate["id"], "pause")
    client.release.set()
    await finish(engine)
    saved_model = "gemini-saved-model"
    engine.get(debate["id"])["model"] = saved_model
    await engine.control(debate["id"], "resume")
    await finish(engine)
    assert len(client.requests) == 4
    assert all(request["model"] == saved_model for request in client.requests[1:])
    assert engine.get(debate["id"])["provider"] == "gemini"
    await engine.close()
    assert client.closed


async def test_legacy_archive_cannot_be_resumed_through_gemini(storage):
    from app.models import DebateConfig

    client = FakeGemini([GeminiError("connection", "Disconnected")])
    engine = Engine(storage, client)
    debate = await engine.create(config(rounds=1))
    await finish(engine)
    archived = engine.get(debate["id"])
    archived["provider"] = "groq"
    archived["model"] = "old-model"
    archived["config"].update(provider="groq", model="old-model")
    engine.save(archived)
    original = json.dumps(storage.get(debate["id"]), sort_keys=True)
    for action in ["resume", "step"]:
        with pytest.raises(Conflict):
            await engine.control(debate["id"], action)
    assert len(client.requests) == 1
    assert json.dumps(storage.get(debate["id"]), sort_keys=True) == original
    # The same scenario can start a separate Gemini experiment.
    copied = DebateConfig.model_validate(archived["config"])
    fresh = await engine.create(copied)
    await finish(engine)
    assert fresh["id"] != debate["id"]
    assert fresh["provider"] == "gemini"
    await engine.close()


async def test_stop_before_worker_starts_and_double_start(storage):
    engine = Engine(storage, FakeGemini(block=True))
    debate = await engine.create(config(rounds=1))
    with pytest.raises(Conflict):
        await engine.create(config(rounds=1))
    await engine.control(debate["id"], "stop")
    assert storage.get(debate["id"])["status"] == "stopped"
    assert engine.active_id is None


def test_rate_limit_backoff_respects_longer_provider_delay():
    assert [simulation.rate_limit_delay(n, None) for n in range(1, 7)] == [
        60,
        120,
        240,
        300,
        300,
        300,
    ]
    assert simulation.rate_limit_delay(1, 0) == 60
    assert simulation.rate_limit_delay(1, 90) == 92
    assert simulation.rate_limit_delay(8, 3600) == 3602
    assert simulation.rate_limit_delay(10000, None) == 300


async def test_rate_limit_keeps_retrying_and_resets_after_success(storage, monkeypatch):
    delays = []
    original_delay = simulation.rate_limit_delay

    def record_delay(retry, retry_after):
        delays.append(original_delay(retry, retry_after))
        return 0  # Exercise the actual retry loop without waiting several minutes.

    monkeypatch.setattr(simulation, "rate_limit_delay", record_delay)
    provider = FakeGemini(
        [GeminiError("rate_limit", "Limit") for _ in range(5)]
        + [{}, GeminiError("rate_limit", "Limit")]
    )
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=1))
    await finish(engine)
    result = storage.get(debate["id"])
    assert result["status"] == "completed"
    assert len(result["messages"]) == 2
    assert len(result["attempts"]) == 8
    assert [a["number"] for a in result["attempts"]] == [1, 2, 3, 4, 5, 6, 1, 2]
    assert delays == [60, 120, 240, 300, 300, 60]
    assert [m["agent_index"] for m in result["messages"]] == [0, 1]
    assert all(request == provider.requests[0] for request in provider.requests[:6])


@pytest.mark.parametrize("action, status", [("pause", "paused"), ("stop", "stopped")])
async def test_wait_can_be_paused_and_stopped_without_waiting(storage, action, status):
    engine = Engine(storage, FakeGemini([GeminiError("rate_limit", "Limit", 3600)]))
    debate = await engine.create(config(rounds=1))
    for _ in range(100):
        if engine.get(debate["id"])["status"] == "waiting":
            break
        await asyncio.sleep(0)
    assert engine.get(debate["id"])["status"] == "waiting"
    assert engine.get(debate["id"])["retry_at"]
    await engine.control(debate["id"], action)
    if action == "pause":
        await finish(engine)
    assert engine.get(debate["id"])["status"] == status
    assert engine.get(debate["id"])["retry_at"] is None
    assert len(engine.get(debate["id"])["attempts"]) == 1
    assert engine.active_id is None


async def test_oversized_request_stops_without_retrying(storage):
    provider = FakeGemini([GeminiError("request_too_large", "Żądanie jest zbyt duże.")])
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=1))
    await finish(engine)
    result = storage.get(debate["id"])
    assert result["status"] == "error"
    assert result["reason"] == "Żądanie jest zbyt duże."
    assert result["retry_at"] is None
    assert len(result["attempts"]) == 1
    assert result["messages"] == []


@pytest.mark.parametrize(
    "response",
    [
        {"content": "", "reasoning": "Tylko rozumowanie"},
        {"content": "Urwany tekst", "finish_reason": "length"},
        {"content": "Urwany strumień", "finish_reason": None},
    ],
)
async def test_incomplete_attempt_is_excluded_on_resume(storage, response):
    provider = FakeGemini([response])
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=1))
    await finish(engine)
    assert engine.get(debate["id"])["status"] == "error"
    assert engine.get(debate["id"])["messages"] == []
    await engine.control(debate["id"], "resume")
    await finish(engine)
    assert len(engine.get(debate["id"])["messages"]) == 2
    assert len(provider.requests[1]["contents"]) == 1


async def test_annotations_and_restart_preserve_transcript(tmp_path):
    path = str(tmp_path / "restart.sqlite3")
    storage = Storage(path)
    provider = FakeGemini(block=True)
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
    new_provider = FakeGemini()
    second = Engine(reopened, new_provider)
    await second.control(debate["id"], "resume")
    await finish(second)
    assert len(reopened.get(debate["id"])["messages"]) == 2
    assert "Tylko dla badacza" not in json.dumps(new_provider.requests)
    await second.close()
    reopened.close()


async def test_recover_after_unclean_exit(storage):
    engine = Engine(storage, FakeGemini(block=True))
    debate = await engine.create(config(rounds=1))
    await engine.client.started.wait()
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
    engine = Engine(storage, FakeGemini(block=True))
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


async def test_single_step_retries_rate_limit_then_pauses(storage, monkeypatch):
    monkeypatch.setattr(simulation, "rate_limit_delay", lambda retry, retry_after: 0)
    provider = FakeGemini(block=True)
    engine = Engine(storage, provider)
    debate = await engine.create(config(rounds=2))
    await provider.started.wait()
    await engine.control(debate["id"], "pause")
    provider.release.set()
    await finish(engine)
    provider.responses = [GeminiError("rate_limit", "Limit", 0)]
    await engine.control(debate["id"], "step")
    await finish(engine)
    result = storage.get(debate["id"])
    assert result["status"] == "paused"
    assert len(result["messages"]) == 2
    assert len(result["attempts"]) == 3
