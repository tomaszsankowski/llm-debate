import asyncio
import copy

from app.models import Agent, DebateConfig


def config(**updates):
    return DebateConfig(
        topic="Pożyczanie rzeczy",
        question="Czy trzeba pytać przed pożyczeniem?",
        agents=(
            Agent(
                name="Anna",
                role="Właścicielka",
                position="Trzeba pytać.",
                goal="Uzyskać zgodę.",
                instructions="PRYWATNE_A",
            ),
            Agent(
                name="Bartek",
                role="Współpracownik",
                position="Można pożyczyć.",
                goal="Przekonać Annę.",
                instructions="PRYWATNE_B",
            ),
        ),
        **updates,
    )


class FakeProvider:
    configured = True

    def __init__(self, responses=None, block=False):
        self.requests = []
        self.responses = list(responses or [])
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = block
        self.closed = False

    async def stream(self, request):
        self.requests.append(copy.deepcopy(request))
        response = self.responses.pop(0) if self.responses else {}
        if isinstance(response, Exception):
            raise response
        self.started.set()
        yield {
            "content": response.get("content", "Publiczna wypowiedź."),
            "reasoning": response.get("reasoning", "TAJNY_TEKST_ROZUMOWANIA"),
        }
        if self.block:
            await self.release.wait()
        yield {
            "finish_reason": response.get("finish_reason", "stop"),
            "usage": {"prompt_tokens": 200, "completion_tokens": 100},
            "metadata": {"model": request["model"], "system_fingerprint": "test-version"},
        }

    async def close(self):
        self.closed = True


async def finish(engine):
    await asyncio.wait_for(engine.task, timeout=3)
