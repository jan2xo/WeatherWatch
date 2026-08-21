"""Small HTTP adapters for OpenAI-compatible editorial providers.

The adapters know transport only. WeatherWatch rules, facts, validation, and
approval remain outside this module.
"""

import json
import os
import urllib.error
import urllib.request


class ProviderRequestError(RuntimeError):
    pass


def _json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ProviderRequestError("Provider response was not a JSON object.")
    return value


def _extract_content(payload):
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderRequestError("Provider response contained no choices.")
    message = choices[0].get("message", {})
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise ProviderRequestError("Provider response contained no message content.")
    return _json_object(content)


class OpenAICompatibleEditorialProvider:
    def __init__(self, *, name, model, timeout_seconds, api_key_env, base_url):
        self.name = name
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")

    def generate(self, context):
        api_key = os.getenv(self.api_key_env, "").strip()
        if not api_key:
            raise ProviderRequestError(f"{self.name} credential is not configured.")
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the WeatherWatch editorial writer. Return only a JSON object "
                        "with headline, caption, generation_mode, and memory_references. "
                        "Canonical weather facts are authoritative.\n"
                        + json.dumps(context, ensure_ascii=False, sort_keys=True)
                    ),
                },
                {"role": "user", "content": "Write the WeatherWatch editorial draft."},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "WeatherWatch/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in {408, 409, 429} or error.code >= 500:
                raise ProviderRequestError(f"{self.name} temporary HTTP {error.code}.") from error
            raise ProviderRequestError(f"{self.name} rejected the request with HTTP {error.code}.") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderRequestError(f"{self.name} request failed.") from error
        result = _extract_content(payload)
        result.setdefault("generation_mode", "ai_assisted")
        result.setdefault("model", self.model)
        return result


def build_provider_from_config(provider):
    name = provider["name"]
    endpoint = {
        "openrouter": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "openai": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "provider_2": os.getenv("AI_PROVIDER_2_BASE_URL", ""),
        "provider_3": os.getenv("AI_PROVIDER_3_BASE_URL", ""),
    }.get(name, "")
    api_key_env = provider.get("credential_reference") or {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "provider_2": "AI_PROVIDER_2_API_KEY",
        "provider_3": "AI_PROVIDER_3_API_KEY",
    }.get(name, "")
    if not endpoint:
        raise ProviderRequestError(f"{name} endpoint is not configured.")
    return OpenAICompatibleEditorialProvider(
        name=name,
        model=provider["model"],
        timeout_seconds=provider["timeout_seconds"],
        api_key_env=api_key_env,
        base_url=endpoint,
    )
