"""Small HTTP adapters for OpenAI-compatible editorial providers.

The adapters know transport only. WeatherWatch rules, facts, validation, and
approval remain outside this module.
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class ProviderRequestError(RuntimeError):
    pass


PROVIDER_BASE_URL_ENV = {
    "openrouter": "OPENROUTER_BASE_URL",
    "openai": "OPENAI_BASE_URL",
    "provider_2": "AI_PROVIDER_2_BASE_URL",
    "provider_3": "AI_PROVIDER_3_BASE_URL",
}
PROVIDER_DEFAULT_BASE_URL = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}
OPENROUTER_REASONING_ENABLED_ENV = (
    "WEATHERWATCH_AI_OPENROUTER_" "REASONING_ENABLED"
)


def _environment(environ=None):
    return os.environ if environ is None else environ


def _openrouter_reasoning_enabled(environ=None):
    environment = _environment(environ)
    value = str(
        environment.get(OPENROUTER_REASONING_ENABLED_ENV, "false")
    ).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ProviderRequestError(
        f"{OPENROUTER_REASONING_ENABLED_ENV} must be a boolean value."
    )


def resolve_provider_endpoint(provider, environ=None):
    environment = _environment(environ)
    name = provider["name"]
    reference = PROVIDER_BASE_URL_ENV.get(name, "")
    endpoint = ""
    if reference:
        endpoint = str(environment.get(reference, "")).strip()
    if not endpoint:
        endpoint = str(provider.get("endpoint", "")).strip()
    if not endpoint:
        endpoint = PROVIDER_DEFAULT_BASE_URL.get(name, "")
    if not endpoint:
        raise ProviderRequestError(f"{name} endpoint is not configured.")

    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderRequestError(f"{name} endpoint configuration is invalid.")
    return endpoint.rstrip("/")


def get_provider_runtime_status(provider, environ=None):
    environment = _environment(environ)
    name = provider["name"]
    credential_reference = provider.get("credential_reference", "")
    endpoint_reference = PROVIDER_BASE_URL_ENV.get(name) or None
    try:
        resolve_provider_endpoint(provider, environ=environment)
        endpoint_configured = True
    except ProviderRequestError:
        endpoint_configured = False
    key_configured = bool(
        credential_reference
        and str(environment.get(credential_reference, "")).strip()
    )
    return {
        "endpoint_reference": endpoint_reference,
        "endpoint_configured": endpoint_configured,
        "key_configured": key_configured,
        "runtime_ready": bool(
            provider.get("enabled")
            and provider.get("model")
            and endpoint_configured
            and key_configured
        ),
    }


def _json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProviderRequestError(
            "Provider message content was not valid JSON."
        ) from error
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
    def __init__(
        self,
        *,
        name,
        model,
        timeout_seconds,
        api_key_env,
        base_url,
        environ=None,
    ):
        self.name = name
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.environ = os.environ if environ is None else environ

    def generate(self, context):
        api_key = str(self.environ.get(self.api_key_env, "")).strip()
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
        if self.name == "openrouter" and _openrouter_reasoning_enabled(self.environ):
            body["reasoning"] = {"enabled": True}
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


def build_provider_from_config(provider, environ=None):
    environment = _environment(environ)
    name = provider["name"]
    endpoint = resolve_provider_endpoint(provider, environ=environment)
    api_key_env = provider.get("credential_reference") or {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "provider_2": "AI_PROVIDER_2_API_KEY",
        "provider_3": "AI_PROVIDER_3_API_KEY",
    }.get(name, "")
    if not api_key_env or not str(environment.get(api_key_env, "")).strip():
        raise ProviderRequestError(f"{name} credential is not configured.")
    return OpenAICompatibleEditorialProvider(
        name=name,
        model=provider["model"],
        timeout_seconds=provider["timeout_seconds"],
        api_key_env=api_key_env,
        base_url=endpoint,
        environ=environment,
    )
