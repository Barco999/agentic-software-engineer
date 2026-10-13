import json
from urllib.parse import urlsplit

from llm.provider import HTTPProvider, ProviderError, instructions


class OpenAIProvider(HTTPProvider):
    name = "openai-compatible"

    def generate(self, role: str, schema: dict, context: dict):
        key = self.settings.openai_api_key.get_secret_value()
        model = self.settings.openai_model
        base = self.settings.openai_base_url.rstrip("/")
        if not key or not model:
            raise ProviderError("openai_credential_or_model_missing")
        parsed = urlsplit(base)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        ):
            raise ProviderError("openai_base_url_requires_https_or_loopback")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError("openai_base_url_invalid")
        # JSON mode maximizes compatibility. All responses are locally schema-validated.
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": instructions(role, schema, context)},
                {"role": "user", "content": json.dumps(context)},
            ],
        }
        if self.settings.openai_json_mode:
            body["response_format"] = {"type": "json_object"}
        response = self.request(
            base + "/chat/completions",
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            body,
            {"run_id": context.get("run_id"), "revision": context.get("revision"), "role": role},
        )
        try:
            message = response["choices"][0]["message"]
            if message.get("refusal"):
                raise ProviderError("openai_refusal")
            return json.loads(message["content"]), {
                "model": model,
                "usage": response.get("usage", {}),
            }
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ProviderError("openai_output_missing_or_invalid") from exc
