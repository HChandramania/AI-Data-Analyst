"""Provider failures are classified without leaking SDK payloads; no network."""

import asyncio
import json
import logging

import httpx
import pytest
from google.genai import errors

from app.config import Settings
from app.planner import GeminiProvider, ProviderFailure, ProviderTimeout


@pytest.mark.parametrize("operation", ["plan", "embed"])
@pytest.mark.parametrize(
    "kind,status,reason",
    [
        ("api", 400, "provider_api_error"),
        ("api", 429, "provider_api_error"),
        ("api", 504, "provider_api_error"),
        ("transport", None, "provider_transport_timeout"),
        ("unexpected", None, "provider_unexpected_error"),
    ],
)
def test_provider_failure_is_safe_and_clients_close(monkeypatch, caplog, operation, kind, status, reason):
    secret = "private-api-key-and-prompt"
    failure = (
        errors.APIError(status, {"error": {"message": secret}})
        if kind == "api"
        else httpx.ReadTimeout(secret)
        if kind == "transport"
        else RuntimeError(secret)
    )
    closed = []

    class Models:
        async def generate_content(self, **kwargs):
            raise failure

        async def embed_content(self, **kwargs):
            raise failure

    class AsyncClient:
        models = Models()

        async def aclose(self):
            closed.append("async")

    class Client:
        aio = AsyncClient()

        def __init__(self, **kwargs):
            pass

        def close(self):
            closed.append("sync")

    monkeypatch.setattr("app.planner.genai.Client", Client)
    caplog.set_level(logging.INFO, logger="dbo.operations")
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key=secret))
    call = provider.plan(secret, []) if operation == "plan" else provider.embed(secret, task_type="RETRIEVAL_QUERY")
    expected = ProviderTimeout if status == 504 or kind == "transport" else ProviderFailure
    with pytest.raises(expected) as caught:
        asyncio.run(call)
    assert secret not in str(caught.value)
    assert closed == ["async", "sync"]
    logs = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "dbo.operations" and "reason" in json.loads(record.message)
    ]
    assert len(logs) == 1 and logs[0]["reason"] == reason
    assert logs[0].get("status") == status
    assert secret not in json.dumps(logs)
