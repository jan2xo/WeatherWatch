import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from services.ai_provider_adapters import OpenAICompatibleEditorialProvider


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        assert request["model"] == "synthetic-model"
        body = json.dumps({
            "choices": [{"message": {"content": json.dumps({
                "headline": "Synthetic headline",
                "caption": "Synthetic caption",
                "generation_mode": "ai_assisted",
                "memory_references": [],
            })}}]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        provider = OpenAICompatibleEditorialProvider(
            name="synthetic",
            model="synthetic-model",
            timeout_seconds=2,
            api_key_env="SYNTHETIC_KEY",
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
        )
        import os
        os.environ["SYNTHETIC_KEY"] = "synthetic-only"
        result = provider.generate({"weather_facts": {"wind_kmh": 20}})
        assert result["headline"] == "Synthetic headline"
        assert result["model"] == "synthetic-model"
    finally:
        server.shutdown()
    print("provider adapter verification ok")


if __name__ == "__main__":
    main()
