"""Strumieniowe Gemini REST API; ponowienia wykonuje silnik debaty."""

import json
from collections.abc import AsyncIterator

import httpx

from .provider import ProviderError, retry_delay


async def sse_events(response: httpx.Response) -> AsyncIterator[dict]:
    data = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            yield json.loads("\n".join(data))
            data.clear()
    if data:
        yield json.loads("\n".join(data))


def api_error(status: int, body: dict, headers) -> ProviderError:
    # Raw messages can contain prompts or credentials. Only classifications are persisted.
    detail = body.get("error", {})
    if status == 429:
        delays = [retry_delay(headers)]
        for item in detail.get("details", []):
            if item.get("@type", "").endswith("google.rpc.RetryInfo"):
                raw = item.get("retryDelay", "")
                if isinstance(raw, str) and raw.endswith("s"):
                    delays.append(retry_delay({"retry-after": raw[:-1]}))
        return ProviderError(
            "rate_limit",
            "Osiągnięto limit API Gemini. Oczekiwanie na ponowienie.",
            max((delay for delay in delays if delay is not None), default=None),
        )
    reasons = {item.get("reason") for item in detail.get("details", [])}
    if status == 401 or "API_KEY_INVALID" in reasons:
        return ProviderError("authentication", "Gemini odrzucił klucz. Sprawdź GEMINI_API_KEY.")
    if status == 403:
        return ProviderError("permission", "Konto Gemini nie ma dostępu do modelu lub projektu.")
    if status == 404:
        return ProviderError("model_unavailable", "Wybrany model nie jest dostępny w Gemini.")
    if status == 413:
        return ProviderError(
            "request_too_large",
            "Gemini odrzucił zbyt duże żądanie. Samo czekanie nie pomoże. Historia nie została skrócona.",
        )
    if status in {400, 422}:
        return ProviderError(
            "invalid_request",
            f"Gemini odrzucił żądanie (HTTP {status}). Sprawdź dostęp do modelu, limit generacji i długość kontekstu. Historia nie została skrócona.",
        )
    return ProviderError(
        "provider_error", f"Błąd usługi Gemini (HTTP {status}). Można wznowić debatę."
    )


def parse_chunk(data: dict) -> dict:
    candidates = data.get("candidates") or []
    candidate = candidates[0] if candidates else {}
    parts = (candidate.get("content") or {}).get("parts") or []
    finish = candidate.get("finishReason")
    metadata = {
        key: data[key] for key in ("responseId", "modelVersion", "createTime") if key in data
    }
    if finish:
        metadata["provider_finish_reason"] = finish
    if data.get("promptFeedback"):
        # Store the block classification, not any free-form feedback text.
        metadata["block_reason"] = data["promptFeedback"].get("blockReason")
    raw_usage = data.get("usageMetadata")
    usage = None
    if raw_usage is not None:
        usage = {
            "prompt_tokens": raw_usage.get("promptTokenCount", 0),
            "completion_tokens": raw_usage.get("candidatesTokenCount", 0)
            + raw_usage.get("thoughtsTokenCount", 0),
            "total_tokens": raw_usage.get("totalTokenCount", 0),
            "reasoning_tokens": raw_usage.get("thoughtsTokenCount", 0),
            "provider_usage": raw_usage,
        }
    return {
        "content": "".join(part.get("text", "") for part in parts if not part.get("thought")),
        "reasoning": "".join(part.get("text", "") for part in parts if part.get("thought")),
        "finish_reason": {"STOP": "stop", "MAX_TOKENS": "length"}.get(finish, finish),
        "metadata": metadata,
        "usage": usage,
    }


class GeminiProvider:
    def __init__(self, api_key: str):
        self.configured = bool(api_key.strip())
        self.client = (
            httpx.AsyncClient(
                base_url="https://generativelanguage.googleapis.com/v1beta/",
                headers={"x-goog-api-key": api_key.strip()},
                timeout=120,
            )
            if self.configured
            else None
        )

    async def stream(self, request: dict) -> AsyncIterator[dict]:
        if not self.client:
            raise ProviderError(
                "missing_key",
                "Brak klucza GEMINI_API_KEY. Uzupełnij .env i odtwórz kontener aplikacji.",
            )
        body = {key: value for key, value in request.items() if key != "model"}
        try:
            async with self.client.stream(
                "POST",
                f"models/{request['model']}:streamGenerateContent",
                params={"alt": "sse"},
                json=body,
            ) as response:
                if response.is_error:
                    await response.aread()
                    try:
                        error_body = response.json()
                    except ValueError:
                        error_body = {}
                    raise api_error(response.status_code, error_body, response.headers)
                async for data in sse_events(response):
                    if "error" in data:
                        raise api_error(data["error"].get("code", 500), data, response.headers)
                    chunk = parse_chunk(data)
                    yield chunk
                    if chunk["metadata"].get("block_reason") or chunk["finish_reason"] in {
                        "SAFETY",
                        "BLOCKLIST",
                        "PROHIBITED_CONTENT",
                        "RECITATION",
                        "SPII",
                    }:
                        raise ProviderError(
                            "blocked",
                            "Gemini zablokował generowanie odpowiedzi. Próba została zapisana; sprawdź scenariusz i profile agentów.",
                        )
        except httpx.HTTPError:
            raise ProviderError(
                "connection",
                "Przerwano połączenie z Gemini lub upłynął czas oczekiwania. Można wznowić debatę.",
            ) from None
        except (ValueError, KeyError, TypeError):
            raise ProviderError(
                "stream_error",
                "Gemini zwrócił nieprawidłowy strumień odpowiedzi. Można wznowić debatę.",
            ) from None

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
