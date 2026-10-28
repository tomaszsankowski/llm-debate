from fastapi.testclient import TestClient

from app.main import create_app
from app.prompts import TRAITS, build_request, system_prompt
from tests.helpers import FakeProvider, config


def test_config_validation_preview_and_exports(tmp_path):
    provider = FakeProvider(block=True)
    app = create_app(str(tmp_path / "api.sqlite3"), provider=provider)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["api_key_configured"]
        data = config(rounds=1).model_dump(mode="json")
        preview = client.post("/api/prompts/preview", json=data).json()
        assert "PRYWATNE_A" in preview["agents"][0]
        assert "PRYWATNE_B" not in preview["agents"][0]
        assert client.post("/api/debates", json={**data, "rounds": 0}).status_code == 422
        assert (
            client.post("/api/debates", json={**data, "agents": data["agents"][:1]}).status_code
            == 422
        )
        response = client.post("/api/debates", json=data)
        assert response.status_code == 201
        debate_id = response.json()["id"]
        assert client.post("/api/debates", json=data).status_code == 409
        assert client.get("/api/debates/not-found").status_code == 404
        assert (
            client.patch(
                f"/api/debates/{debate_id}/annotations",
                json={"notes": "Notatka", "outcome": "consensus"},
            ).status_code
            == 200
        )
        client.post(f"/api/debates/{debate_id}/control", json={"action": "stop"})
        exported = client.get(f"/api/debates/{debate_id}/export")
        assert "attachment" in exported.headers["content-disposition"]
        result = exported.json()
        assert result["config"] == data
        assert result["annotations"]["notes"] == "Notatka"
        assert result["schema_version"] == 1
        assert result["status"] == "stopped"
        assert client.get("/api/debates?q=nowa").json()[0]["id"] == debate_id
        assert client.get("/api/debates?q=brak").json() == []
        assert "api_key" not in exported.text.lower()
        assert client.get(f"/api/debates/{debate_id}/attempts/missing").status_code == 404
    with TestClient(create_app(str(tmp_path / "api.sqlite3"), provider=FakeProvider())) as client:
        assert client.get(f"/api/debates/{debate_id}").json()["config"] == data
        assert (
            client.get(f"/api/debates/{debate_id}").json()["annotations"]["outcome"] == "consensus"
        )


def test_missing_key_and_static_frontend(tmp_path):
    provider = FakeProvider()
    provider.configured = False
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>Test</h1>")
    with TestClient(create_app(str(tmp_path / "db"), provider, str(dist))) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json()["api_key_configured"] is False
        assert client.post("/api/debates", json=config().model_dump(mode="json")).status_code == 409
        assert client.get("/api/debates").json() == []
        assert client.get("/api/unknown").status_code == 404


def test_traits_and_reasoning_are_independent():
    data = config()
    for key, definition in TRAITS.items():
        assert len(definition["instructions"]) == 5
        for value in range(1, 6):
            setattr(data.agents[0].traits, key, value)
            assert definition["instructions"][value - 1] in system_prompt(data, 0)
    off = build_request(data, 0, [])
    data.agents[0].reasoning = True
    on = build_request(data, 0, [])
    assert off["reasoning_effort"] == "none"
    assert on["reasoning_effort"] == "low"
    assert on["reasoning_format"] == "parsed"
    assert not {"temperature", "top_p", "seed"} & on.keys()


def test_legacy_word_target_does_not_change_prompts_or_exported_config(tmp_path):
    from app.models import DebateConfig

    data = config().model_dump(mode="json")
    legacy = {**data, "target_words": 100}
    restored = DebateConfig.model_validate(legacy)
    assert restored.model_dump(mode="json") == data
    assert legacy["target_words"] == 100  # archived snapshots are not modified
    request = build_request(restored, 0, [])
    assert request["max_completion_tokens"] == 2048
    assert "słów" not in request["messages"][0]["content"]
    assert "2048" not in request["messages"][0]["content"]
    with TestClient(
        create_app(str(tmp_path / "legacy.sqlite3"), provider=FakeProvider())
    ) as client:
        current = client.post("/api/prompts/preview", json=data)
        previous = client.post("/api/prompts/preview", json=legacy)
        assert previous.status_code == 200
        assert previous.json() == current.json()
