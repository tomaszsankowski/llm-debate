import asyncio
import json

import httpx
import pytest

from app.gemini_client import GeminiProvider
from app.prompts import build_request
from app.provider import ProviderError
from tests.helpers import config


def test_gemini_request_keeps_profiles_and_public_history_separate():
    data = config(provider="gemini")
    history = [
        {"agent_index": 0, "content": "Pierwszy argument."},
        {"agent_index": 1, "content": "Odpowiedź rozmówcy."},
    ]
    request = build_request(data, 0, history)
    assert "PRYWATNE_A" in request["systemInstruction"]["parts"][0]["text"]
    assert "PRYWATNE_B" not in json.dumps(request)
    assert [item["role"] for item in request["contents"]] == ["user", "model", "user"]
    assert data.opening in request["contents"][0]["parts"][0]["text"]
    assert len(request["contents"][-1]["parts"]) == 2
    assert request["contents"][1]["parts"][0]["text"].endswith("Pierwszy argument.")
    assert request["generationConfig"]["maxOutputTokens"] == 2048
    assert request["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "minimal",
        "includeThoughts": False,
    }
    data.agents[0].reasoning = True
    assert build_request(data, 0, history)["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "low",
        "includeThoughts": True,
    }
    assert not {"temperature", "topP", "seed"} & request["generationConfig"].keys()


async def test_stream_request_usage_reasoning_and_credentials():
    payload = build_request(config(provider="gemini"), 0, [])
    response = None

    async def handle(request):
        nonlocal response
        assert request.url.path.endswith(f"/{payload['model']}:streamGenerateContent")
        assert dict(request.url.params) == {"alt": "sse"}
        assert request.headers["x-goog-api-key"] == "test-secret"
        assert json.loads(request.content) == {
            key: value for key, value in payload.items() if key != "model"
        }
        events = [
            {"candidates": [{"content": {"parts": [{"thought": True, "text": "Analiza"}]}}]},
            {
                "candidates": [
                    {"content": {"parts": [{"text": "Odpowiedź"}]}, "finishReason": "STOP"}
                ]
            },
            {
                "responseId": "response-1",
                "modelVersion": payload["model"],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 20,
                    "thoughtsTokenCount": 5,
                    "totalTokenCount": 35,
                },
            },
        ]
        # Includes a comment, split data lines and a final event without a blank delimiter.
        lines = [": heartbeat\n\n"]
        for event in events:
            pretty = json.dumps(event, ensure_ascii=False, indent=2)
            lines.append("\n".join("data: " + line for line in pretty.splitlines()))
        response = httpx.Response(
            200, text="\n\n".join(lines), headers={"content-type": "text/event-stream"}
        )
        return response

    provider = GeminiProvider("")
    provider.client = httpx.AsyncClient(
        base_url="https://generativelanguage.googleapis.com/v1beta/",
        headers={"x-goog-api-key": "test-secret"},
        transport=httpx.MockTransport(handle),
    )
    chunks = [chunk async for chunk in provider.stream(payload)]
    assert chunks[0]["reasoning"] == "Analiza"
    assert chunks[0]["content"] == ""
    assert chunks[1]["content"] == "Odpowiedź"
    assert chunks[1]["finish_reason"] == "stop"
    assert chunks[2]["usage"]["completion_tokens"] == 25
    assert chunks[2]["usage"]["reasoning_tokens"] == 5
    assert chunks[2]["usage"]["total_tokens"] == 35
    assert chunks[2]["metadata"]["responseId"] == "response-1"
    assert "test-secret" not in json.dumps(chunks)
    assert response.is_closed
    await provider.close()
    assert provider.client.is_closed


@pytest.mark.parametrize(
    "status, code",
    [
        (400, "invalid_request"),
        (401, "authentication"),
        (403, "permission"),
        (404, "model_unavailable"),
        (413, "request_too_large"),
        (429, "rate_limit"),
        (500, "provider_error"),
    ],
)
async def test_http_errors_are_sanitized_and_retry_info_is_respected(status, code):
    async def handle(request):
        return httpx.Response(
            status,
            headers={"retry-after": "10"},
            json={
                "error": {
                    "message": "test-secret",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "90.5s",
                        }
                    ],
                }
            },
        )

    provider = GeminiProvider("")
    provider.client = httpx.AsyncClient(
        base_url="https://example.test/", transport=httpx.MockTransport(handle)
    )
    with pytest.raises(ProviderError) as info:
        async for _ in provider.stream(build_request(config(provider="gemini"), 0, [])):
            pass
    assert info.value.code == code
    assert "test-secret" not in json.dumps(info.value.as_dict())
    if status == 429:
        assert info.value.retry_after == 90.5
    await provider.close()


@pytest.mark.parametrize(
    "event, code",
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked"),
        ({"candidates": [{"finishReason": "SAFETY"}]}, "blocked"),
        ({"error": {"code": 429, "message": "test-secret"}}, "rate_limit"),
    ],
)
async def test_stream_errors_are_not_successful_replies(event, code):
    provider = GeminiProvider("")
    provider.client = httpx.AsyncClient(
        base_url="https://example.test/",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=f"data: {json.dumps(event)}\n\n")
        ),
    )
    with pytest.raises(ProviderError) as info:
        async for _ in provider.stream(build_request(config(provider="gemini"), 0, [])):
            pass
    assert info.value.code == code
    assert "test-secret" not in str(info.value)
    await provider.close()


async def test_output_limit_does_not_publish_partial_turn(tmp_path):
    from app.simulation import Engine
    from app.storage import Storage
    from tests.helpers import finish

    provider = GeminiProvider("")
    provider.configured = True
    event = {
        "candidates": [
            {"content": {"parts": [{"text": "Nieukończona"}]}, "finishReason": "MAX_TOKENS"}
        ]
    }
    provider.client = httpx.AsyncClient(
        base_url="https://example.test/",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=f"data: {json.dumps(event)}\n\n")
        ),
    )
    storage = Storage(str(tmp_path / "limit.sqlite3"))
    engine = Engine(storage, {"gemini": provider})
    try:
        debate = await engine.create(config(provider="gemini", rounds=1))
        await finish(engine)
        result = engine.get(debate["id"])
        assert result["status"] == "error"
        assert result["messages"] == []
        assert result["attempts"][0]["content"] == "Nieukończona"
        assert result["attempts"][0]["finish_reason"] == "length"
        assert result["attempts"][0]["metadata"]["provider_finish_reason"] == "MAX_TOKENS"
    finally:
        await engine.close()
        storage.close()


async def test_stopping_gemini_closes_stream_and_keeps_partial_attempt(tmp_path):
    from app.simulation import Engine
    from app.storage import Storage

    class BlockingStream(httpx.AsyncByteStream):
        def __init__(self):
            self.started = asyncio.Event()
            self.closed = False

        async def __aiter__(self):
            self.started.set()
            yield b'data: {"candidates":[{"content":{"parts":[{"text":"Fragment"}]}}]}\n\n'
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    stream = BlockingStream()
    provider = GeminiProvider("")
    provider.configured = True
    provider.client = httpx.AsyncClient(
        base_url="https://example.test/",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
    )
    storage = Storage(str(tmp_path / "stop.sqlite3"))
    engine = Engine(storage, {"gemini": provider})
    try:
        debate = await engine.create(config(provider="gemini", rounds=1))
        await asyncio.wait_for(stream.started.wait(), timeout=3)
        await engine.control(debate["id"], "stop")
        result = engine.get(debate["id"])
        assert stream.closed
        assert result["status"] == "stopped"
        assert result["messages"] == []
        assert result["attempts"][0]["status"] == "interrupted"
        assert result["attempts"][0]["content"] == "Fragment"
    finally:
        await engine.close()
        storage.close()
