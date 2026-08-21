import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage.state_repository import (
    JsonStateRepository,
    RedisStateRepository,
    get_state_backend_name,
    get_state_repository,
)


def test_restart_recovery():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        repository = JsonStateRepository(path)
        repository.save({"status": "approved", "retry": 2, "provenance": {"mode": "templated"}})
        restarted = JsonStateRepository(path)
        assert restarted.load(lambda: {})["status"] == "approved"
        assert restarted.load(lambda: {})["retry"] == 2


def test_missing_and_corrupt_state_are_distinct():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        repository = JsonStateRepository(path)
        assert repository.load(lambda: {"empty": True}) == {"empty": True}
        path.write_text("{not-json", encoding="utf-8")
        try:
            repository.load(dict)
        except RuntimeError as error:
            assert "not replaced" in str(error)
        else:
            raise AssertionError("Corrupt state must not become empty state")


def test_atomic_save_keeps_valid_json():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        repository = JsonStateRepository(path)
        repository.save({"value": "persisted"})
        assert json.loads(path.read_text(encoding="utf-8")) == {"value": "persisted"}


class FakeRedisStateRepository(RedisStateRepository):
    values = {}

    def _command(self, *parts):
        command = parts[0]
        if command == "GET":
            return self.values.get(parts[1])
        if command == "SET":
            self.values[parts[1]] = parts[2]
            return "OK"
        raise AssertionError(command)


def test_external_repository_round_trip_and_namespace():
    first = FakeRedisStateRepository("redis://localhost", "weatherwatch:approval_state")
    second = FakeRedisStateRepository("redis://localhost", "weatherwatch:facebook_token_state")
    first.save({"current": {"status": "approved"}, "history": []})
    assert first.load(dict)["current"]["status"] == "approved"
    assert second.load(lambda: {"missing": True}) == {"missing": True}


class FakeRespServer:
    def __init__(self, *, password="secret", error=None):
        self.password = password
        self.error = error
        self.commands = []
        self.values = {2: {"weatherwatch:state": json.dumps({"status": "ready"})}}
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.listener.close()
        self.thread.join(timeout=2)

    @staticmethod
    def _read_exact(connection, size):
        data = b""
        while len(data) < size:
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise RuntimeError("fake RESP client disconnected")
            data += chunk
        return data

    def _readline(self, connection):
        data = b""
        while not data.endswith(b"\r\n"):
            data += self._read_exact(connection, 1)
        return data[:-2]

    def _command(self, connection):
        assert self._read_exact(connection, 1) == b"*"
        count = int(self._readline(connection))
        parts = []
        for _ in range(count):
            assert self._read_exact(connection, 1) == b"$"
            size = int(self._readline(connection))
            parts.append(self._read_exact(connection, size).decode())
            assert self._read_exact(connection, 2) == b"\r\n"
        return parts

    @staticmethod
    def _send(connection, value):
        connection.sendall(value.encode() + b"\r\n")

    def _run(self):
        try:
            connection, _ = self.listener.accept()
        except OSError:
            return
        with connection:
            database = 0
            authenticated = False
            try:
                while True:
                    parts = self._command(connection)
                    self.commands.append(parts)
                    command = parts[0].upper()
                    if command == "AUTH":
                        authenticated = parts[-1] == self.password
                        self._send(connection, "+OK" if authenticated else "-ERR invalid password")
                    elif self.error:
                        self._send(connection, self.error)
                    elif command == "SELECT":
                        database = int(parts[1])
                        self._send(connection, "+OK")
                    elif command == "GET":
                        if self.password and not authenticated:
                            self._send(connection, "-NOAUTH Authentication required")
                        else:
                            value = self.values.get(database, {}).get(parts[1])
                            if value is None:
                                self._send(connection, "$-1")
                            else:
                                encoded = value.encode()
                                self._send(connection, f"${len(encoded)}\r\n{value}")
                    elif command == "SET":
                        self.values.setdefault(database, {})[parts[1]] = parts[2]
                        self._send(connection, "+OK")
                    else:
                        self._send(connection, "-ERR unsupported")
            except (RuntimeError, OSError):
                pass


def test_real_resp_session_boundary():
    server = FakeRespServer()
    server.start()
    repository = RedisStateRepository(
        f"redis://:{'secret'}@127.0.0.1:{server.port}/2",
        "weatherwatch:state",
    )
    try:
        assert repository.load(dict)["status"] == "ready"
        assert [item[0] for item in server.commands] == ["AUTH", "SELECT", "GET"]
    finally:
        server.close()

    server = FakeRespServer()
    server.start()
    repository = RedisStateRepository(
        f"redis://:{'secret'}@127.0.0.1:{server.port}/2",
        "weatherwatch:state",
    )
    try:
        repository.save({"status": "saved"})
        assert [item[0] for item in server.commands] == ["AUTH", "SELECT", "SET"]
        assert server.values[2]["weatherwatch:state"] == '{"status":"saved"}'
    finally:
        server.close()


def test_resp_error_does_not_leak_connection_details():
    server = FakeRespServer(error="-ERR backend unavailable")
    server.start()
    url = f"redis://:{'secret'}@127.0.0.1:{server.port}/2"
    repository = RedisStateRepository(url, "weatherwatch:state")
    try:
        try:
            repository.load(dict)
        except RuntimeError as error:
            message = str(error)
            assert "secret" not in message
            assert url not in message
        else:
            raise AssertionError("RESP error must be mapped")
    finally:
        server.close()


def test_backend_selection_is_explicit():
    original = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    try:
        os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        assert get_state_backend_name() == "filesystem"
        os.environ["WEATHERWATCH_STATE_BACKEND"] = "unknown"
        try:
            get_state_backend_name()
        except ValueError as error:
            assert "Unsupported" in str(error)
        else:
            raise AssertionError("Unknown backend must fail clearly")
    finally:
        if original is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original


def test_redis_backend_requires_url():
    original_backend = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    original_url = os.environ.get("WEATHERWATCH_REDIS_URL")
    try:
        os.environ["WEATHERWATCH_STATE_BACKEND"] = "redis"
        os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        try:
            get_state_repository(Path("/tmp/p15-state.json"), state_key="test")
        except ValueError as error:
            assert "WEATHERWATCH_REDIS_URL" in str(error)
        else:
            raise AssertionError("Redis backend without URL must fail clearly")
    finally:
        if original_backend is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original_backend
        if original_url is None:
            os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        else:
            os.environ["WEATHERWATCH_REDIS_URL"] = original_url


if __name__ == "__main__":
    test_restart_recovery()
    test_missing_and_corrupt_state_are_distinct()
    test_atomic_save_keeps_valid_json()
    test_external_repository_round_trip_and_namespace()
    test_real_resp_session_boundary()
    test_resp_error_does_not_leak_connection_details()
    test_backend_selection_is_explicit()
    test_redis_backend_requires_url()
    print("state repository verification ok")
