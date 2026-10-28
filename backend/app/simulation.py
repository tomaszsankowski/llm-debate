import asyncio
import copy
import logging
import secrets
import time
from collections import defaultdict
from contextlib import aclosing, suppress
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .models import PROVIDERS, Annotation, DebateConfig
from .prompts import PROMPT_VERSION, build_request
from .provider import ProviderError
from .storage import Storage

logger = logging.getLogger(__name__)
TERMINAL = {"completed", "stopped"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rate_limit_delay(retry: int, retry_after: float | None) -> float:
    # Slow down after repeated refusals, but never retry before the provider allows it.
    backoff = min(60 * 2 ** min(retry - 1, 3), 300)
    return max(backoff, (retry_after or 0) + 2)


class Conflict(Exception):
    pass


class Engine:
    def __init__(self, storage: Storage, provider):
        self.storage = storage
        self.providers = provider if isinstance(provider, dict) else {"groq": provider}
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None
        self.current: dict | None = None
        self.pause_requested = False
        self.single_step = False
        self.wake = asyncio.Event()
        self.listeners: dict[str, set[asyncio.Queue]] = defaultdict(set)

    @property
    def active_id(self) -> str | None:
        return self.current["id"] if self.task and not self.task.done() else None

    def get(self, debate_id: str) -> dict:
        if self.current and self.current["id"] == debate_id:
            return self.current
        return self.storage.get(debate_id)

    def view(self, debate_id: str) -> dict:
        debate = self.get(debate_id)
        # Large input histories remain available in the export and attempt endpoint.
        result = {key: value for key, value in debate.items() if key != "attempts"}
        result["attempts"] = [
            {key: value for key, value in attempt.items() if key != "request"}
            for attempt in debate["attempts"]
        ]
        return result

    def save(self, debate: dict) -> None:
        debate["updated_at"] = now()
        debate["revision"] += 1
        self.storage.save(debate)
        for queue in self.listeners.get(debate["id"], set()):
            if queue.empty():
                queue.put_nowait(True)

    def subscribe(self, debate_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self.listeners[debate_id].add(queue)
        return queue

    def unsubscribe(self, debate_id: str, queue: asyncio.Queue) -> None:
        self.listeners[debate_id].discard(queue)
        if not self.listeners[debate_id]:
            del self.listeners[debate_id]

    def check_idle(self) -> None:
        if self.active_id:
            raise Conflict("Inna generacja już trwa. Wstrzymaj lub zatrzymaj aktywną debatę.")

    def require_provider(self, provider_id: str):
        provider = self.providers.get(provider_id)
        if not provider or not provider.configured:
            key = PROVIDERS[provider_id]["key_env"]
            raise Conflict(f"Brak klucza {key}. Uzupełnij .env i odtwórz kontener aplikacji.")
        return provider

    async def create(self, config: DebateConfig) -> dict:
        async with self.lock:
            self.check_idle()
            self.require_provider(config.provider)
            timestamp = now()
            first = (
                secrets.randbelow(2)
                if config.first_speaker == "random"
                else "AB".index(config.first_speaker)
            )
            debate = {
                "schema_version": 1,
                "prompt_version": PROMPT_VERSION,
                "id": str(uuid4()),
                "created_at": timestamp,
                "updated_at": timestamp,
                "revision": 0,
                "provider": config.provider,
                "model": config.model,
                "config": config.model_dump(mode="json"),
                "first_agent": first,
                "status": "paused",
                "reason": None,
                "retry_at": None,
                "messages": [],
                "attempts": [],
                "annotations": Annotation().model_dump(),
            }
            self.save(debate)
            self.launch(debate, step=False)
            return self.view(debate["id"])

    def launch(self, debate: dict, step: bool) -> None:
        self.current = debate
        self.pause_requested = False
        self.single_step = step
        self.wake = asyncio.Event()
        debate.update(status="running", reason=None, retry_at=None)
        self.save(debate)
        self.task = asyncio.create_task(self.run(debate), name=f"debate:{debate['id']}")

    async def control(self, debate_id: str, action: str) -> dict:
        async with self.lock:
            debate = self.get(debate_id)
            if action in {"resume", "step"}:
                self.check_idle()
                if debate["status"] in TERMINAL:
                    raise Conflict(
                        "Ta debata jest zakończona. Można użyć jej ustawień w nowej debacie."
                    )
                self.require_provider(debate["provider"])
                self.launch(debate, step=action == "step")
            elif action == "pause":
                if self.active_id != debate_id:
                    raise Conflict("Ta debata nie jest uruchomiona.")
                self.pause_requested = True
                debate["status"] = "pausing"
                self.save(debate)
                self.wake.set()
            elif action == "stop":
                if debate["status"] in TERMINAL:
                    return self.view(debate_id)
                if self.active_id == debate_id and self.task:
                    self.task.cancel()
                    with suppress(asyncio.CancelledError):
                        await self.task
                debate.update(status="stopped", reason="Zatrzymano ręcznie.", retry_at=None)
                self.save(debate)
            return self.view(debate_id)

    async def delete(self, debate_id: str) -> None:
        async with self.lock:
            if self.active_id == debate_id:
                raise Conflict("Przed usunięciem wstrzymaj lub zatrzymaj debatę.")
            self.storage.delete(debate_id)
            if self.current and self.current["id"] == debate_id:
                self.current = None
            for queue in self.listeners.get(debate_id, set()):
                if queue.empty():
                    queue.put_nowait(True)

    def annotate(self, debate_id: str, annotation: Annotation) -> dict:
        debate = self.get(debate_id)
        debate["annotations"] = annotation.model_dump()
        self.save(debate)
        return debate["annotations"]

    async def generate(self, debate: dict, config: DebateConfig, index: int) -> dict:
        turn = len(debate["messages"]) + 1
        attempt = {
            "id": str(uuid4()),
            "prompt_version": PROMPT_VERSION,
            "agent_index": index,
            "turn": turn,
            "round": (turn + 1) // 2,
            "number": 1 + sum(item["turn"] == turn for item in debate["attempts"]),
            "status": "streaming",
            "started_at": now(),
            "finished_at": None,
            "duration_ms": None,
            "content": "",
            "reasoning": "",
            "usage": None,
            "metadata": {},
            "finish_reason": None,
            "error": None,
            "request": build_request(config, index, debate["messages"]),
        }
        debate["attempts"].append(attempt)
        self.save(debate)
        started = time.monotonic()
        last_save = started
        try:
            provider = self.require_provider(debate["provider"])
            async with aclosing(provider.stream(copy.deepcopy(attempt["request"]))) as stream:
                async for chunk in stream:
                    attempt["content"] += chunk.get("content", "")
                    attempt["reasoning"] += chunk.get("reasoning", "")
                    attempt["metadata"].update(chunk.get("metadata", {}))
                    if chunk.get("usage") is not None:
                        attempt["usage"] = chunk["usage"]
                    if chunk.get("finish_reason"):
                        attempt["finish_reason"] = chunk["finish_reason"]
                    if time.monotonic() - last_save >= 0.2:
                        self.save(debate)
                        last_save = time.monotonic()
            if attempt["finish_reason"] != "stop":
                message = (
                    (
                        "Osiągnięto limit generacji. Odpowiedź jest nieukończona. "
                        "Można użyć ustawień w nowej debacie i zwiększyć limit tokenów."
                    )
                    if attempt["finish_reason"] == "length"
                    else ("Strumień zakończył się bez pełnej odpowiedzi. Można wznowić debatę.")
                )
                raise ProviderError("incomplete", message)
            if not attempt["content"].strip():
                raise ProviderError(
                    "empty_response",
                    "Model nie zwrócił publicznej wypowiedzi. Próba została zapisana; można wznowić debatę.",
                )
            attempt["status"] = "completed"
        except asyncio.CancelledError:
            attempt.update(
                status="interrupted",
                error={"code": "interrupted", "message": "Przerwano odbieranie odpowiedzi."},
            )
            raise
        except ProviderError as error:
            attempt.update(status="failed", error=error.as_dict())
            raise
        except Exception:
            attempt.update(
                status="failed",
                error={"code": "internal", "message": "Nie udało się odebrać odpowiedzi."},
            )
            raise
        finally:
            attempt["finished_at"] = now()
            attempt["duration_ms"] = round((time.monotonic() - started) * 1000)
            # A successful attempt and public turn are committed together in run().
            if attempt["status"] != "completed":
                self.save(debate)
        return attempt

    async def run(self, debate: dict) -> None:
        config = DebateConfig.model_validate(
            {**debate["config"], "provider": debate["provider"], "model": debate["model"]}
        )
        retries = 0
        try:
            while len(debate["messages"]) < config.rounds * 2:
                index = (debate["first_agent"] + len(debate["messages"])) % 2
                try:
                    attempt = await self.generate(debate, config, index)
                except ProviderError as error:
                    if error.code == "rate_limit":
                        retries += 1
                        delay = rate_limit_delay(retries, error.retry_after)
                        debate.update(
                            status="waiting",
                            reason=f"Limit API — oczekiwanie na automatyczne ponowienie nr {retries}.",
                            retry_at=(
                                datetime.now(timezone.utc) + timedelta(seconds=delay)
                            ).isoformat(),
                        )
                        self.save(debate)
                        if not self.pause_requested:
                            with suppress(TimeoutError):
                                await asyncio.wait_for(self.wake.wait(), timeout=delay)
                        if self.pause_requested:
                            debate.update(
                                status="paused",
                                reason="Wstrzymano przed ponowieniem.",
                                retry_at=None,
                            )
                            self.save(debate)
                            return
                        debate.update(status="running", reason=None, retry_at=None)
                        self.save(debate)
                        continue
                    debate.update(status="error", reason=error.message, retry_at=None)
                    self.save(debate)
                    return
                retries = 0
                debate["messages"].append(
                    {
                        "id": str(uuid4()),
                        "attempt_id": attempt["id"],
                        "agent_index": index,
                        "turn": attempt["turn"],
                        "round": attempt["round"],
                        "content": attempt["content"],
                        "created_at": now(),
                    }
                )
                # No await between committing a turn and deciding whether to pause.
                if len(debate["messages"]) == config.rounds * 2:
                    debate.update(status="completed", reason="Osiągnięto limit rund.")
                elif self.pause_requested or self.single_step:
                    debate.update(status="paused", reason=None)
                self.save(debate)
                if debate["status"] in {"paused", "completed"}:
                    return
                await asyncio.sleep(0)  # let pending controls run before another request
                if self.pause_requested:
                    debate.update(status="paused", reason=None)
                    self.save(debate)
                    return
        except asyncio.CancelledError:
            debate.update(status="interrupted", reason="Przerwano generowanie.", retry_at=None)
            self.save(debate)
            raise
        except Exception as error:
            # Log only the type; provider exceptions may contain sensitive request data.
            logger.error("Debate engine failed: %s", type(error).__name__)
            debate.update(
                status="error",
                reason="Wewnętrzny błąd generowania. Zapisane tury pozostają dostępne.",
                retry_at=None,
            )
            self.save(debate)

    async def close(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            if self.current and self.current["status"] in {"running", "pausing", "waiting"}:
                self.current.update(
                    status="interrupted", reason="Zatrzymano backend.", retry_at=None
                )
                self.save(self.current)
        for provider in self.providers.values():
            await provider.close()
