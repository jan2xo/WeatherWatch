import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_provider_adapters import (
    OpenAICompatibleEditorialProvider,
    ProviderRequestError,
)


MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
REASONING_SENTINEL = "synthetic-private-reasoning"


def _provider_response(content, *, reasoning_details=None):
    message = {"content": content}
    if reasoning_details is not None:
        message["reasoning_details"] = reasoning_details
    return {"choices": [{"message": message}]}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.server.requests.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": json.loads(self.rfile.read(length)),
            }
        )
        body = json.dumps(self.server.responses.pop(0)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _build_provider(server, *, name="openrouter", environ=None, model=MODEL):
    return OpenAICompatibleEditorialProvider(
        name=name,
        model=model,
        timeout_seconds=2,
        api_key_env="SYNTHETIC_KEY",
        base_url=f"http://127.0.0.1:{server.server_address[1]}",
        environ={"SYNTHETIC_KEY": "synthetic-only", **(environ or {})},
    )


def _valid_content(headline="Synthetic headline"):
    return json.dumps(
        {
            "headline": headline,
            "caption": "Synthetic caption",
            "generation_mode": "ai_assisted",
            "memory_references": [],
        }
    )


def verify_openrouter_payload_and_response_isolation(server):
    server.responses.extend(
        [
            _provider_response(_valid_content("Default reasoning off")),
            _provider_response(
                _valid_content("Reasoning enabled"),
                reasoning_details=[
                    {"type": "reasoning.text", "text": REASONING_SENTINEL}
                ],
            ),
        ]
    )

    default_result = _build_provider(server).generate(
        {"weather_facts": {"wind_kmh": 20}}
    )
    default_request = server.requests[-1]
    assert default_request["path"] == "/chat/completions"
    assert default_request["body"]["model"] == MODEL
    assert default_request["body"]["response_format"] == {"type": "json_object"}
    assert "reasoning" not in default_request["body"]
    assert default_request["headers"]["Authorization"] == "Bearer synthetic-only"
    assert default_result["model"] == MODEL

    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        enabled_result = _build_provider(
            server,
            environ={"WEATHERWATCH_AI_OPENROUTER_REASONING_ENABLED": "true"},
        ).generate({"weather_facts": {"wind_kmh": 20}})
    enabled_request = server.requests[-1]
    assert enabled_request["body"]["model"] == MODEL
    assert enabled_request["body"]["reasoning"] == {"enabled": True}
    assert enabled_request["body"]["response_format"] == {"type": "json_object"}
    assert enabled_result["headline"] == "Reasoning enabled"
    assert REASONING_SENTINEL not in json.dumps(enabled_result)
    assert REASONING_SENTINEL not in stdout.getvalue()
    assert REASONING_SENTINEL not in stderr.getvalue()
    assert "synthetic-only" not in stdout.getvalue()
    assert "synthetic-only" not in stderr.getvalue()


def verify_non_openrouter_providers_unchanged(server):
    for name in ("openai", "provider_2", "provider_3"):
        server.responses.append(_provider_response(_valid_content(name)))
        result = _build_provider(
            server,
            name=name,
            environ={"WEATHERWATCH_AI_OPENROUTER_REASONING_ENABLED": "true"},
            model=f"{name}/exact-model",
        ).generate({"weather_facts": {"wind_kmh": 20}})
        request = server.requests[-1]
        assert request["body"]["model"] == f"{name}/exact-model"
        assert request["body"]["response_format"] == {"type": "json_object"}
        assert "reasoning" not in request["body"]
        assert result["model"] == f"{name}/exact-model"


def verify_strict_response_and_flag_validation(server):
    for content in ("not-json", "[]"):
        server.responses.append(_provider_response(content))
        try:
            _build_provider(server).generate({"weather_facts": {}})
        except ProviderRequestError:
            pass
        else:
            raise AssertionError("Malformed or non-object provider content must fail")

    try:
        _build_provider(
            server,
            environ={"WEATHERWATCH_AI_OPENROUTER_REASONING_ENABLED": "perhaps"},
        ).generate({"weather_facts": {}})
    except ProviderRequestError as error:
        assert "boolean" in str(error)
    else:
        raise AssertionError("Invalid OpenRouter reasoning override must fail")


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.responses = []
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        verify_openrouter_payload_and_response_isolation(server)
        verify_non_openrouter_providers_unchanged(server)
        verify_strict_response_and_flag_validation(server)
    finally:
        server.shutdown()
    print("provider adapter verification ok")


if __name__ == "__main__":
    main()
