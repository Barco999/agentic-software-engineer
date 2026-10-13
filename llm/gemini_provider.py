import json
import re

from llm.provider import HTTPProvider, ProviderError, instructions


class GeminiProvider(HTTPProvider):
    name = "gemini"

    def generate(self, role: str, schema: dict, context: dict):
        key = self.settings.gemini_api_key.get_secret_value()
        model = self.settings.gemini_model
        if not key or not model:
            raise ProviderError("gemini_credential_or_model_missing")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
            raise ProviderError("gemini_model_id_invalid")
        body = {
                "systemInstruction": {
                        "parts": [
                            {
                                "text": (
                                    instructions(role, schema, context)
                                    + (
                                        "\nMANDATORY PLANNING CONTRACT:\n"
                                        "Generate exactly six tasks with IDs: "
                                        "REQ, ARCH, CODE, TEST, DOCS, RELEASE.\n"
                                        "Every task MUST include these dependencies:\n"
                                        "REQ: []\n"
                                        "ARCH: [REQ]\n"
                                        "CODE: [ARCH]\n"
                                        "TEST: [CODE]\n"
                                        "DOCS: [TEST]\n"
                                        "RELEASE: [DOCS]\n"
                                        "These dependencies are mandatory safety requirements. "
                                        "Do not remove or replace them. "
                                        "Use the dependencies as JSON arrays of strings.\n"
                                        "Customize descriptions, acceptance criteria, "
                                        "and other permitted task fields for the user requirement."
                                    )
                                    if role == "planning"
                                    else instructions(role, schema, context)
                                )
                            }
                        ]
                },
                "contents": [{"role": "user", "parts": [{"text": json.dumps(context)}]}],
                "generationConfig": {
                    "maxOutputTokens": 8192 if context.get("custom_generation") else 4096,
                    "responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": schema}},
                },
        }
        response = self.request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"x-goog-api-key": key, "Content-Type": "application/json"},
            body,
            {"run_id": context.get("run_id"), "revision": context.get("revision"), "role": role},
        )
        try:
            parts = response["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            return json.loads(text), {"model": model, "usage": response.get("usageMetadata", {})}
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ProviderError("gemini_output_missing_or_invalid") from exc
