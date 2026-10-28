import json

import groq
import httpx
import pytest

from app.groq_client import GroqProvider
from app.prompts import build_request
from app.provider import ProviderError, retry_delay
from tests.helpers import config


async def test_real_sdk_parses_stream_and_closes_without_leaking_key():
    request_body = None

    async def handle(request):
        nonlocal request_body
        request_body = json.loads(request.content)
        chunks = [
            {
                "id": "completion-1",
                "model": "qwen/qwen3.8-27b",
                "created": 1,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"reasoning": "Analiza"}}],
            },
            {
                "id": "completion-1",
                "model": "qwen/qwen3.8-27b",
                "created": 1,
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "delta": {"content": "Odpowiedź"}, "finish_reason": "stop"}
                ],
                "x_groq": {
                    "id": "request-1",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                },
            },
        ]
        return httpx.Response(
            200,
            text="".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    provider = GroqProvider("")
    provider.client = groq.AsyncGroq(
        api_key="test-secret", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    payload = build_request(config(), 0, [])
    chunks = [chunk async for chunk in provider.stream(payload)]
    assert chunks[0]["reasoning"] == "Analiza"
    assert chunks[1]["content"] == "Odpowiedź"
    assert chunks[1]["usage"]["total_tokens"] == 30
    assert chunks[1]["metadata"]["request_id"] == "request-1"
    assert request_body == payload
    assert "test-secret" not in json.dumps(chunks)
    await provider.close()


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "authentication"),
        (403, "permission"),
        (404, "model_unavailable"),
        (400, "invalid_request"),
        (413, "request_too_large"),
        (429, "rate_limit"),
        (500, "provider_error"),
    ],
)
async def test_provider_errors_are_sanitized(status, code):
    async def handle(request):
        return httpx.Response(
            status, json={"error": {"message": "secret-value"}}, headers={"retry-after": "2"}
        )

    provider = GroqProvider("")
    provider.client = groq.AsyncGroq(
        api_key="secret-value",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(ProviderError) as info:
        async for _ in provider.stream(build_request(config(), 0, [])):
            pass
    assert info.value.code == code
    assert "secret-value" not in str(info.value)
    if status == 429:
        assert info.value.retry_after == 2
    await provider.close()


def test_retry_after_formats():
    assert retry_delay({"retry-after": "3.5"}) == 3.5
    assert retry_delay({"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}) == 0
    assert retry_delay({}) is None
    assert retry_delay({"retry-after": "NaN"}) is None
    assert retry_delay({"retry-after": "Infinity"}) is None


async def test_oversized_request_reported_as_429_is_not_retried():
    async def handle(request):
        return httpx.Response(
            429,
            json={
                "error": {
                    "message": "Request too large for model: secret-value",
                    "code": "rate_limit_exceeded",
                }
            },
        )

    provider = GroqProvider("")
    provider.client = groq.AsyncGroq(
        api_key="secret-value",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(ProviderError) as info:
        async for _ in provider.stream(build_request(config(), 0, [])):
            pass
    assert info.value.code == "request_too_large"
    assert info.value.retry_after is None
    assert "secret-value" not in json.dumps(info.value.as_dict())
    await provider.close()
