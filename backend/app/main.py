import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .groq_client import GroqProvider
from .models import MODEL_ID, Annotation, Control, DebateConfig
from .prompts import LEVELS, PROMPT_VERSION, TRAITS, system_prompt
from .simulation import Conflict, Engine, now
from .storage import Storage


def create_app(
    database_path: str | None = None, provider=None, frontend_dist: str | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage = Storage(database_path or os.getenv("DATABASE_PATH", "data/debates.sqlite3"))
        storage.recover(now())
        engine = Engine(storage, provider or GroqProvider(os.getenv("GROQ_API_KEY", "")))
        app.state.engine = engine
        try:
            yield
        finally:
            await engine.close()
            storage.close()

    app = FastAPI(title="llm-debate", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(KeyError)
    async def missing_record(request: Request, error: KeyError):
        return JSONResponse(
            {"detail": "Nie znaleziono debaty lub próby generowania."}, status_code=404
        )

    @app.exception_handler(Conflict)
    async def conflict(request: Request, error: Conflict):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def invalid_data(request: Request, error: RequestValidationError):
        fields = [".".join(str(part) for part in item["loc"][1:]) for item in error.errors()]
        return JSONResponse(
            {"detail": "Sprawdź wymagane pola i zakresy wartości.", "fields": fields},
            status_code=422,
        )

    def engine() -> Engine:
        return app.state.engine

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "api_key_configured": engine().provider.configured,
            "model": MODEL_ID,
            "active_debate_id": engine().active_id,
        }

    @app.get("/api/settings")
    async def settings():
        return {
            "model": MODEL_ID,
            "prompt_version": PROMPT_VERSION,
            "traits": TRAITS,
            "levels": LEVELS,
        }

    @app.post("/api/prompts/preview")
    async def preview(config: DebateConfig):
        return {
            "prompt_version": PROMPT_VERSION,
            "agents": [system_prompt(config, i) for i in range(2)],
            "opening": config.opening,
        }

    @app.get("/api/debates")
    async def debates(q: str = ""):
        return [item for item in engine().storage.list() if q.casefold() in item["name"].casefold()]

    @app.post("/api/debates", status_code=201)
    async def create_debate(config: DebateConfig):
        return await engine().create(config)

    @app.get("/api/debates/{debate_id}")
    async def debate(debate_id: str):
        return engine().view(debate_id)

    @app.post("/api/debates/{debate_id}/control")
    async def control(debate_id: str, command: Control):
        return await engine().control(debate_id, command.action)

    @app.patch("/api/debates/{debate_id}/annotations")
    async def annotate(debate_id: str, annotation: Annotation):
        return engine().annotate(debate_id, annotation)

    @app.get("/api/debates/{debate_id}/attempts/{attempt_id}")
    async def attempt(debate_id: str, attempt_id: str):
        for item in engine().get(debate_id)["attempts"]:
            if item["id"] == attempt_id:
                return item
        raise KeyError(attempt_id)

    @app.get("/api/debates/{debate_id}/export")
    async def export(debate_id: str):
        data = engine().get(debate_id)
        return Response(
            json.dumps(data, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="debata-{data["id"]}.json"'},
        )

    @app.get("/api/debates/{debate_id}/events")
    async def events(debate_id: str, request: Request):
        engine().get(debate_id)

        async def stream():
            queue = engine().subscribe(debate_id)
            try:
                while not await request.is_disconnected():
                    data = engine().view(debate_id)
                    yield f"id: {data['revision']}\nevent: snapshot\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    while True:
                        try:
                            await asyncio.wait_for(queue.get(), timeout=15)
                            break
                        except TimeoutError:
                            yield ": heartbeat\n\n"
                            if await request.is_disconnected():
                                return
            finally:
                engine().unsubscribe(debate_id, queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    dist = Path(
        frontend_dist
        or os.getenv(
            "FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")
        )
    )
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    async def index():
        if not (dist / "index.html").is_file():
            raise HTTPException(
                503, "Brak zbudowanego interfejsu. Uruchom aplikację przez Docker Compose."
            )
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
