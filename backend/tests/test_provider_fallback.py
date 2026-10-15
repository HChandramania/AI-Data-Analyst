"""Mock-only fallback routing and independent execution security boundaries."""

import asyncio
import json

import httpx
import pytest
from test_phase2 import headers, setup
from test_phase2 import phase2_client as client_fixture

from app.config import Settings, load_runtime_settings
from app.planner import (
    AnalysisPlan,
    DashboardPlan,
    GeminiProvider,
    ProviderFailure,
    ProviderMalformed,
    ProviderTimeout,
    ProviderUnavailable,
)

phase2_client = client_fixture


def install_http(monkeypatch, handler):
    real_client = httpx.AsyncClient
    clients = []

    def client(**kwargs):
        result = real_client(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(result)
        return result

    monkeypatch.setattr("app.planner.httpx.AsyncClient", client)
    return clients


@pytest.mark.parametrize("dashboard", [False, True])
def test_order_schema_and_no_secret_logs(monkeypatch, caplog, dashboard):
    calls = []
    settings = Settings(
        _env_file=None, gemini_api_key="secret-gemini", openrouter_api_key="secret-router", groq_api_key="secret-groq"
    )
    provider = GeminiProvider(settings)

    async def gemini(*args):
        calls.append("gemini")
        raise ProviderFailure("sanitized failure")

    monkeypatch.setattr(provider, "_gemini_generate", gemini)
    valid = {"action": "clarify", "dataset_ids": [], "question": "Which measure?"}
    if dashboard:
        valid = {"cards": [{"title": "Clarify", "plan": valid}]}

    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert "confirmed_joins" in body["messages"][1]["content"]
        assert "SQL must use columns[].id" in body["messages"][1]["content"]
        assert "date FIRST and format SECOND" in body["messages"][1]["content"]
        assert "$defs" in body["messages"][0]["content"]
        if request.url.host == "openrouter.ai":
            calls.append("openrouter")
            assert request.headers["authorization"] == "Bearer secret-router"
            return httpx.Response(503, json={"error": "secret-router"})
        calls.append("groq")
        assert request.headers["authorization"] == "Bearer secret-groq"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(valid)}}]})

    clients = install_http(monkeypatch, handler)
    result = asyncio.run(
        provider.dashboard("question", [{"confirmed_joins": []}])
        if dashboard
        else provider.plan("question", [{"confirmed_joins": []}])
    )
    assert isinstance(result, DashboardPlan if dashboard else AnalysisPlan)
    assert calls == ["gemini", "openrouter", "groq"]
    assert all(client.is_closed for client in clients)
    assert "secret-router" not in caplog.text and "secret-groq" not in caplog.text


def test_malformed_primary_falls_back_and_success_stops(monkeypatch):
    provider = GeminiProvider(Settings(_env_file=None, openrouter_api_key="router", groq_api_key="groq"))
    calls = []

    def handler(request):
        calls.append(request.url.host)
        content = "{}" if len(calls) == 1 else '{"action":"clarify","dataset_ids":[],"question":"Which measure?"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    install_http(monkeypatch, handler)
    assert asyncio.run(provider.plan("question", [])).action == "clarify"
    assert calls == ["openrouter.ai", "api.groq.com"]
    monkeypatch.undo()
    calls.clear()

    def success(request):
        calls.append(request.url.host)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"action":"unsupported","dataset_ids":[]}'}}]}
        )

    install_http(monkeypatch, success)
    assert asyncio.run(provider.plan("question", [])).action == "unsupported"
    assert calls == ["openrouter.ai"]


def test_shared_deadline_and_cancellation(monkeypatch):
    settings = Settings(_env_file=None, gemini_api_key="a", openrouter_api_key="b", groq_api_key="c").model_copy(
        update={"provider_timeout_seconds": 0.09}
    )
    provider = GeminiProvider(settings)
    calls = []

    async def slow(*args):
        calls.append(args[0] if isinstance(args[0], str) and args[0] in {"openrouter", "groq"} else "gemini")
        await asyncio.sleep(1)

    monkeypatch.setattr(provider, "_gemini_generate", slow)
    monkeypatch.setattr(provider, "_compatible_generate", slow)

    async def run():
        start = asyncio.get_running_loop().time()
        with pytest.raises(ProviderTimeout):
            await provider.plan("question", [])
        assert asyncio.get_running_loop().time() - start < 0.5
        assert calls == ["gemini", "openrouter", "groq"]
        calls.clear()
        task = asyncio.create_task(provider.plan("question", []))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert "openrouter" not in calls and "groq" not in calls

    asyncio.run(run())


def test_runtime_keys_models_reload_and_removal(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DBO_OPENROUTER_API_KEY=router\nDBO_GROQ_API_KEY=groq\nDBO_GROQ_MODEL=custom-model\n")
    loaded = load_runtime_settings(Settings(_env_file=None), env)
    assert loaded.openrouter_api_key.get_secret_value() == "router"
    assert loaded.groq_model == "custom-model"
    env.write_text("DBO_OPENROUTER_MODEL=new-model\n")
    removed = load_runtime_settings(loaded, env)
    assert removed.openrouter_api_key is None and removed.groq_api_key is None
    assert removed.openrouter_model == "new-model"


@pytest.mark.parametrize("unsafe", [False, True])
def test_fallback_api_execution_still_validates_sql(phase2_client, monkeypatch, unsafe):
    client = phase2_client
    dataset, conversation = setup(client)
    client.app.state.provider = GeminiProvider(Settings(_env_file=None, openrouter_api_key="router"))

    def handler(request):
        sql = (
            "SELECT * FROM read_csv('/private')"
            if unsafe
            else f"SELECT SUM(c8) AS revenue_usd FROM dataset_{dataset['id'].replace('-', '')}"
        )
        plan = {"action": "query", "dataset_ids": [dataset["id"]], "sql": sql}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan)}}]})

    install_http(monkeypatch, handler)
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages", headers=headers(client), json={"question": "Revenue?"}
    )
    if unsafe:
        assert response.status_code == 422 and response.json()["error"]["code"] == "SQL_REJECTED"
    else:
        assert response.status_code == 200, response.text
        assert response.json()["data"]["table"]["rows"] == [{"revenue_usd": "3760.00"}]


def test_oversized_response_rejected(monkeypatch):
    provider = GeminiProvider(Settings(_env_file=None, groq_api_key="groq"))
    install_http(monkeypatch, lambda request: httpx.Response(200, content=b"x" * (128 * 1024 + 1)))
    with pytest.raises(ProviderMalformed):
        asyncio.run(provider.plan("question", []))


def test_embeddings_do_not_switch_providers(monkeypatch):
    provider = GeminiProvider(Settings(_env_file=None, openrouter_api_key="router", groq_api_key="groq"))

    def forbidden(request):
        pytest.fail("Embedding must not reach planning fallback")

    install_http(monkeypatch, forbidden)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.embed("query", task_type="RETRIEVAL_QUERY"))
