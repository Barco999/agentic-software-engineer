import json

import httpx
import pytest
from pydantic import SecretStr

from llm.provider import LLMClient, ProviderError
from orchestration.state import RequirementsArtifact

OUTPUT = {
    "functional": ["shorten URL"],
    "nonfunctional": ["safe"],
    "assumptions": [],
    "open_questions": [],
    "acceptance_criteria": ["redirect"],
    "risk_level": "medium",
    "needs_clarification": False,
}


def test_gemini_request_and_structured_output(settings):
    settings.gemini_api_key = SecretStr("fake-key-for-mock")
    settings.gemini_model = "configured-model"

    def handler(request):
        body = json.loads(request.content)
        assert request.headers["x-goog-api-key"] == "fake-key-for-mock"
        assert body["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(OUTPUT)}]}}],
                "usageMetadata": {"totalTokenCount": 20},
            },
        )

    artifact, usage = LLMClient(settings, transport=httpx.MockTransport(handler)).generate(
        "requirements", RequirementsArtifact, {"scenario": "greenfield"}
    )
    assert artifact.functional == ["shorten URL"]
    assert usage["usage"]["totalTokenCount"] == 20


def test_openai_compatible_request_and_output(settings):
    settings.llm_provider = "openai"
    settings.openai_api_key = SecretStr("fake-key-for-mock")
    settings.openai_model = "configured-model"

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert json.loads(request.content)["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(OUTPUT)}}],
                "usage": {"total_tokens": 10},
            },
        )

    artifact, usage = LLMClient(settings, transport=httpx.MockTransport(handler)).generate(
        "requirements", RequirementsArtifact, {"scenario": "greenfield"}
    )
    assert artifact.risk_level == "medium"
    assert usage["provider"] == "openai-compatible"


def test_provider_retry_is_bounded(settings, monkeypatch):
    settings.gemini_api_key = SecretStr("fake-key")
    settings.gemini_model = "configured-model"
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(503, json={})

    monkeypatch.setattr("llm.provider.time.sleep", lambda value: None)
    with pytest.raises(ProviderError, match="provider_http_503"):
        LLMClient(settings, transport=httpx.MockTransport(handler)).generate(
            "requirements", RequirementsArtifact, {"scenario": "greenfield"}
        )
    assert len(attempts) == 3


def test_bad_model_json_never_passes_schema_gate(settings):
    settings.gemini_api_key = SecretStr("fake-key")
    settings.gemini_model = "configured-model"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"unexpected":true}'}]}}]}
        )
    )
    with pytest.raises(ProviderError, match="schema_invalid"):
        LLMClient(settings, transport=transport).generate("requirements", RequirementsArtifact, {})


def test_transient_provider_failure_recovers_and_emits_retry_metadata(settings, monkeypatch):
    settings.gemini_api_key = SecretStr("fake-key")
    settings.gemini_model = "configured-model"
    attempts, retries = [], []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, json={})
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(OUTPUT)}]}}]}
        )

    monkeypatch.setattr("llm.provider.time.sleep", lambda value: None)
    client = LLMClient(
        settings,
        transport=httpx.MockTransport(handler),
        on_retry=lambda attempt, reason, context: retries.append((attempt, reason, context)),
    )
    client.generate("requirements", RequirementsArtifact, {"run_id": "mock-run", "revision": 1})
    assert len(attempts) == 2
    assert retries[0][1] == "provider_http_429"
    assert retries[0][2]["role"] == "requirements"
