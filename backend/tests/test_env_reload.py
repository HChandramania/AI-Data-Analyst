"""Root Compose env edits are applied to the next analytical request."""

import json
from pathlib import Path

import pytest
from test_phase2 import headers, setup
from test_phase2 import phase2_client as client_fixture

from app import analysis
from app.config import RuntimeConfigError, Settings, load_runtime_settings
from app.planner import AnalysisPlan, GeminiProvider
from app.sql_policy import validate_sql

phase2_client = client_fixture


def write_env(path: Path, *, key: str = "test-key", model: str = "fixture-model", query_timeout: int = 5):
    path.write_text(
        f"DBO_GEMINI_API_KEY={key}\nDBO_GEMINI_MODEL={model}\n"
        f"DBO_PROVIDER_TIMEOUT_SECONDS=12\nDBO_QUERY_TIMEOUT_SECONDS={query_timeout}\n",
        encoding="utf-8",
    )


def test_runtime_snapshot_validates_edits_removals_and_missing_file(tmp_path):
    env_file = tmp_path / ".env"
    base = Settings(_env_file=None, gemini_api_key="stale-container-value")
    write_env(env_file)
    first = load_runtime_settings(base, env_file)
    assert first.gemini_api_key.get_secret_value() == "test-key"
    assert first.query_timeout_seconds == 5
    write_env(env_file, key="new-key", query_timeout=9)
    second = load_runtime_settings(base, env_file)
    assert second.gemini_api_key.get_secret_value() == "new-key"
    assert second.query_timeout_seconds == 9
    env_file.write_text("DBO_GEMINI_MODEL=fixture-model\n", encoding="utf-8")
    assert load_runtime_settings(base, env_file).gemini_api_key is None
    write_env(env_file, query_timeout=999)
    with pytest.raises(RuntimeConfigError):
        load_runtime_settings(base, env_file)
    write_env(env_file, model="   ")
    with pytest.raises(RuntimeConfigError):
        load_runtime_settings(base, env_file)
    env_file.unlink()
    with pytest.raises(RuntimeConfigError):
        load_runtime_settings(base, env_file)


def test_case_insensitive_filter_is_read_only_and_column_scoped():
    registry = {"dataset_fixture": {"c5", "c6", "c7"}}
    sql = "SELECT SUM(c6 * c7) AS revenue FROM dataset_fixture WHERE LOWER(c5) = 'south'"
    assert validate_sql(sql, registry) == sql


def test_gemini_reload_through_real_analysis_pipeline(phase2_client, tmp_path, monkeypatch):
    client = phase2_client
    dataset, conversation = setup(client)
    route = f"/api/v1/conversations/{conversation['id']}/messages"
    env_file = tmp_path / ".env"
    write_env(env_file, key="first-key", model="first-model")
    calls = []

    class Models:
        async def generate_content(self, *, model, contents, config):
            assert config.response_json_schema == AnalysisPlan.model_json_schema()
            calls[-1]["model"] = model
            table = f"dataset_{dataset['id'].replace('-', '')}"
            return type(
                "Response",
                (),
                {
                    "text": json.dumps(
                        {
                            "action": "query",
                            "dataset_ids": [dataset["id"]],
                            "sql": f"SELECT SUM(c8) AS revenue_usd FROM {table}",
                        }
                    )
                },
            )()

        async def embed_content(self, *, model, contents, config):
            assert model == "gemini-embedding-001"
            assert config.output_dimensionality == 768
            embedding = type("Embedding", (), {"values": [1.0] + [0.0] * 767})()
            return type("EmbeddingResponse", (), {"embeddings": [embedding]})()

    class AsyncClient:
        models = Models()

        async def aclose(self):
            pass

    class Client:
        aio = AsyncClient()

        def __init__(self, *, api_key, http_options):
            calls.append({"key": api_key, "timeout": http_options.timeout})

        def close(self):
            pass

    monkeypatch.setattr("app.planner.genai.Client", Client)
    client.app.state.provider = GeminiProvider(Settings(_env_file=None, gemini_api_key=None), env_file)
    first = client.post(route, headers=headers(client), json={"question": "Total revenue?"})
    assert first.status_code == 200, first.text
    assert first.json()["data"]["table"]["rows"] == [{"revenue_usd": "3760.00"}]
    assert [call for call in calls if "model" in call] == [
        {"key": "first-key", "timeout": 12000, "model": "first-model"}
    ]

    original_execute = analysis.execute
    query_timeouts = []

    async def capture_timeout(sql, sources, timeout_seconds, capacity):
        query_timeouts.append(timeout_seconds)
        return await original_execute(sql, sources, timeout_seconds, capacity)

    monkeypatch.setattr(analysis, "execute", capture_timeout)
    write_env(env_file, key="second-key", model="second-model", query_timeout=8)
    second = client.post(route, headers=headers(client), json={"question": "Total revenue again?"})
    assert second.status_code == 200, second.text
    assert [call for call in calls if "model" in call][-1] == {
        "key": "second-key",
        "timeout": 12000,
        "model": "second-model",
    }
    assert second.json()["data"]["cache_hit"] is True
    assert query_timeouts == []

    env_file.write_text("DBO_GEMINI_MODEL=second-model\n", encoding="utf-8")
    unavailable = client.post(route, headers=headers(client), json={"question": "Total revenue?"})
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert len([call for call in calls if "model" in call]) == 2

    write_env(env_file, query_timeout=999)
    invalid = client.post(route, headers=headers(client), json={"question": "Total revenue?"})
    assert invalid.status_code == 503
    assert invalid.json()["error"]["code"] == "RUNTIME_CONFIG_INVALID"
    assert len([call for call in calls if "model" in call]) == 2
    saved = client.get(f"/api/v1/conversations/{conversation['id']}").json()["data"]
    assert saved["analyses"][0]["status"] == "complete"
    assert saved["analyses"][-1]["status"] == "failed"
