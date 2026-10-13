"""Discover actual Gemini models; optionally test the project's real JSON provider.

Run from the project folder with its virtual-environment Python. The default
only reads model metadata. --generate explicitly sends one small inference
request using the existing Gemini provider's request schema and parser.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import PROJECT_ROOT, Settings, load_settings  # noqa: E402
from llm.gemini_provider import GeminiProvider  # noqa: E402
from llm.provider import ProviderError  # noqa: E402
from orchestration.audit import redact  # noqa: E402

BASE = "https://generativelanguage.googleapis.com/v1beta"


def safe_text(value: object, credential: str) -> str:
    text = str(value)
    if credential:
        text = text.replace(credential, "[REDACTED]")
    return redact(text[:2000])


def api_error(response: httpx.Response, credential: str) -> dict:
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if not isinstance(error, dict):
            error = {}
    except ValueError:
        error = {}
    return {
        "http_status": response.status_code,
        "api_status": safe_text(error.get("status", "UNKNOWN"), credential),
        "message": safe_text(
            error.get("message", "No structured error message was returned"), credential
        ),
    }


def discover(settings: Settings, transport=None) -> dict:
    credential = settings.gemini_api_key.get_secret_value()
    names = set()
    token = None
    with httpx.Client(
        timeout=min(settings.agent_timeout_seconds, 30),
        transport=transport,
        follow_redirects=False,
    ) as client:
        for _ in range(5):
            parameters = {"pageSize": 1000}
            if token:
                parameters["pageToken"] = token
            response = client.get(
                BASE + "/models",
                headers={"x-goog-api-key": credential},
                params=parameters,
            )
            if response.status_code != 200:
                return {"status": "failed", **api_error(response, credential)}
            if len(response.content) > 1_000_000:
                raise ProviderError("model_metadata_response_too_large")
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("models", []), list):
                raise ProviderError("model_metadata_response_invalid")
            for model in payload.get("models", []):
                if not isinstance(model, dict):
                    continue
                name = model.get("name", "")
                if (
                    isinstance(name, str)
                    and re.fullmatch(r"models/[A-Za-z0-9._-]{1,128}", name)
                    and "generateContent" in model.get("supportedGenerationMethods", [])
                ):
                    names.add(name.removeprefix("models/"))
            token = payload.get("nextPageToken")
            if not token:
                break
            if not isinstance(token, str) or len(token) > 4096:
                raise ProviderError("model_metadata_page_token_invalid")
    model_id = settings.gemini_model
    return {
        "status": "passed",
        "http_status": 200,
        "configured_model_listed_for_generate_content": model_id in names,
        "list_truncated": bool(token),
        "available_generate_content_models": sorted(names),
        "note": "Listing metadata does not verify generation quota or structured-output support.",
    }


class ProbeOutput(BaseModel):
    message: Literal["ok"]


class DiagnosticGeminiProvider(GeminiProvider):
    """Keep the real provider's payload/parser; send one diagnostic attempt."""

    last_error: dict | None = None

    def request(self, url, headers, body, retry_context=None):
        with httpx.Client(
            timeout=self.settings.agent_timeout_seconds,
            transport=self.transport,
            follow_redirects=False,
        ) as client:
            response = client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            self.last_error = api_error(response, self.settings.gemini_api_key.get_secret_value())
            raise ProviderError(f"provider_http_{response.status_code}")
        if response.status_code != 200 or len(response.content) > 1_000_000:
            raise ProviderError("diagnostic_generation_response_invalid")
        return response.json()


def diagnose(settings: Settings, generate=False, transport=None) -> dict:
    credential = settings.gemini_api_key.get_secret_value()
    result = {
        "configuration": {
            "env_file_present": (PROJECT_ROOT / ".env").is_file(),
            "credential_configured": bool(credential.strip()),
            "configured_model": safe_text(settings.gemini_model, credential),
            "provider": settings.llm_provider,
            "demo_mode": settings.demo_mode,
        },
        "generation_test": {"performed": False},
    }
    if not credential.strip():
        result["model_discovery"] = {
            "status": "failed",
            "error": "gemini_credential_missing",
        }
        return result
    try:
        result["model_discovery"] = discover(settings, transport)
    except (httpx.TransportError, ValueError, TypeError, ProviderError) as exc:
        result["model_discovery"] = {
            "status": "failed",
            "error": getattr(exc, "code", type(exc).__name__),
        }
        return result
    discovery = result["model_discovery"]
    if not generate:
        return result
    if discovery["status"] != "passed" or not discovery.get(
        "configured_model_listed_for_generate_content"
    ):
        result["generation_test"]["reason"] = (
            "Choose an exact model ID from the returned list before testing generation."
        )
        return result
    provider = DiagnosticGeminiProvider(settings, transport=transport)
    result["generation_test"] = {"performed": True, "attempt_limit": 1}
    try:
        output, usage = provider.generate(
            "provider_diagnostic",
            ProbeOutput.model_json_schema(),
            {"instruction": "Return the JSON object with message equal to the literal ok."},
        )
        ProbeOutput.model_validate(output)
        result["generation_test"].update(
            {"status": "passed", "message": "ok", "model": safe_text(usage["model"], credential)}
        )
    except (httpx.TransportError, ValueError, TypeError, ProviderError, ValidationError) as exc:
        result["generation_test"].update(
            {
                "status": "failed",
                "error": getattr(exc, "code", type(exc).__name__),
                "details": provider.last_error,
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate", action="store_true", help="Explicitly send one real structured inference test"
    )
    parser.add_argument(
        "--model", help="Test this model in memory; does not change your saved .env"
    )
    args = parser.parse_args()
    try:
        settings = load_settings()
    except (ValueError, OSError):
        print(json.dumps({"error": "configuration_load_failed"}))
        return 1
    if args.model:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", args.model):
            print(json.dumps({"error": "model_id_invalid"}))
            return 1
        settings.gemini_model = args.model
    report = diagnose(settings, args.generate)
    print(json.dumps(report, indent=2))
    success = report["model_discovery"]["status"] == "passed"
    if args.generate:
        success = success and report["generation_test"].get("status") == "passed"
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
