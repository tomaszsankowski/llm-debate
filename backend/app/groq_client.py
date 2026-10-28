from collections.abc import AsyncIterator

import groq
import httpx

from .provider import ProviderError, retry_delay

REQUEST_TOO_LARGE = (
    "Groq odrzucił zbyt duże żądanie. Samo czekanie nie pomoże: potrzebne jest "
    "krótsze wejście lub większy limit usługi. Historia rozmowy nie została skrócona."
)


def request_too_large(error: groq.APIStatusError) -> bool:
    if error.status_code == 413:
        return True
    # Read only the classification; raw provider messages can echo sensitive input.
    body = error.body if isinstance(error.body, dict) else {}
    detail = body.get("error", body)
    message = detail.get("message", "") if isinstance(detail, dict) else ""
    return isinstance(message, str) and message.casefold().startswith("request too large")


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
            if request_too_large(error):
                raise ProviderError("request_too_large", REQUEST_TOO_LARGE) from None
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
            if request_too_large(error):
                raise ProviderError("request_too_large", REQUEST_TOO_LARGE) from None
            if error.status_code in {400, 422}:
                raise ProviderError(
                    "invalid_request",
                    f"Groq odrzucił żądanie (HTTP {error.status_code}). Sprawdź dostępność modelu, limit generacji i długość kontekstu. Historia nie została skrócona.",
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
