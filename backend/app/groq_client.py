import math
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import groq
import httpx


class ProviderError(Exception):
    def __init__(self, code: str, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retry_after": self.retry_after}


def retry_delay(headers) -> float:
    raw = headers.get("retry-after", "")
    try:
        seconds = float(raw)
        if math.isfinite(seconds):
            return max(0, seconds)
    except ValueError:
        pass
    try:
        deadline = parsedate_to_datetime(raw)
        return max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return 10


class GroqProvider:
    def __init__(self, api_key: str):
        self.configured = bool(api_key.strip())
        # Retries belong to the engine, so every attempt is recorded in the export.
        self.client = (
            groq.AsyncGroq(api_key=api_key, max_retries=0, timeout=120) if self.configured else None
        )

    async def stream(self, request: dict) -> AsyncIterator[dict]:
        if not self.client:
            raise ProviderError(
                "missing_key",
                "Brak klucza GROQ_API_KEY. Uzupełnij plik .env i uruchom aplikację ponownie.",
            )
        stream = None
        try:
            options = dict(request)
            # The HTTP API supports stream_options before it is exposed by this SDK.
            stream_options = options.pop("stream_options", None)
            stream = await self.client.chat.completions.create(
                **options, extra_body={"stream_options": stream_options} if stream_options else None
            )
            async for chunk in stream:
                data = chunk.model_dump(exclude_none=True)
                if data.get("error"):
                    raise ProviderError(
                        "stream_error", "Groq przerwał strumień odpowiedzi. Spróbuj wznowić debatę."
                    )
                delta = {}
                if data.get("choices"):
                    choice = data["choices"][0]
                    delta = choice.get("delta", {})
                    if choice.get("finish_reason"):
                        delta["finish_reason"] = choice["finish_reason"]
                metadata = {
                    key: data[key]
                    for key in ("id", "model", "created", "system_fingerprint")
                    if key in data
                }
                x_groq = data.get("x_groq") or {}
                usage = data.get("usage") or x_groq.get("usage")
                if x_groq.get("id"):
                    metadata["request_id"] = x_groq["id"]
                yield {
                    "content": delta.get("content") or "",
                    "reasoning": delta.get("reasoning") or "",
                    "finish_reason": delta.get("finish_reason"),
                    "metadata": metadata,
                    "usage": usage,
                }
        except groq.RateLimitError as error:
            raise ProviderError(
                "rate_limit",
                "Osiągnięto limit API Groq. Oczekiwanie na ponowienie.",
                retry_delay(error.response.headers),
            ) from None
        except groq.AuthenticationError:
            raise ProviderError(
                "authentication", "Groq odrzucił klucz API. Sprawdź GROQ_API_KEY w pliku .env."
            ) from None
        except groq.PermissionDeniedError:
            raise ProviderError(
                "permission", "Konto Groq nie ma dostępu do wybranego modelu."
            ) from None
        except groq.NotFoundError:
            raise ProviderError(
                "model_unavailable", "Wybrany model nie jest dostępny w Groq."
            ) from None
        except groq.APIStatusError as error:
            # Do not persist raw provider errors: they can echo credentials or input.
            if error.status_code in {400, 413, 422}:
                raise ProviderError(
                    "invalid_request",
                    "Groq odrzucił żądanie. Sprawdź dostępność modelu, limit generacji i długość kontekstu. Historia nie została skrócona.",
                ) from None
            raise ProviderError(
                "provider_error",
                f"Błąd usługi Groq (HTTP {error.status_code}). Można wznowić debatę.",
            ) from None
        except (groq.APIConnectionError, httpx.HTTPError):
            raise ProviderError(
                "connection",
                "Przerwano połączenie z Groq lub upłynął czas oczekiwania. Można wznowić debatę.",
            ) from None
        finally:
            if stream is not None:
                await stream.close()

    async def close(self) -> None:
        if self.client:
            await self.client.close()
