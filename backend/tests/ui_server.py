"""Deterministyczny dostawca wyłącznie dla testów przeglądarkowych, bez kluczy API."""

import asyncio
import tempfile
from pathlib import Path

import uvicorn

from app.main import create_app


class BrowserTestProvider:
    configured = True

    async def stream(self, request):
        is_anna = "Nazwa: Anna" in request["messages"][0]["content"]
        text = (
            "Uważam, że przed pożyczeniem moich rzeczy należy zapytać. "
            "Potrzebowałam długopisu i nie wiedziałam, gdzie go szukać. "
            "Rozumiem, że spotkanie było pilne, ale krótka wiadomość pozwoliłaby uniknąć problemu."
            if is_anna
            else "Rozumiem, że brak długopisu sprawił ci kłopot. Uważałem, że chwilowe pożyczenie "
            "zwykłej rzeczy jest w porządku. Twój argument o dostępności jest jednak przekonujący. "
            "Następnym razem zapytam lub skorzystam z długopisu ze wspólnej szuflady."
        )
        if request["reasoning_effort"] != "none":
            yield {"reasoning": "Testowy materiał do analizy — nie trafia do kontekstu rozmówcy."}
        for word in text.split(" "):
            await asyncio.sleep(0.08)
            yield {"content": word + " "}
        yield {
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 300, "completion_tokens": 90},
            "metadata": {"model": request["model"], "system_fingerprint": "browser-test-fixture"},
        }

    async def close(self):
        pass


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parents[2] / ".test-data"
    data_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data_dir) as temporary:
        application = create_app(
            str(Path(temporary) / "ui.sqlite3"), provider=BrowserTestProvider()
        )
        uvicorn.run(application, host="127.0.0.1", port=8765, timeout_graceful_shutdown=2)
