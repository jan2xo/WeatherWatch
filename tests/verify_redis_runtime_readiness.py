import os
import socket
import ssl
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.runtime_paths import runtime_path
import storage.facebook_token_store as facebook_token_store
from storage.state_repository import (
    RedisStateRepository,
    get_state_backend_status,
    get_state_repository,
)


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def close(self):
        self.closed = True


class FailingTlsContext:
    def wrap_socket(self, raw_socket, *, server_hostname):
        assert server_hostname == "redis.example"
        raise ssl.SSLError("synthetic TLS failure")


class WrappedTlsContext:
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def wrap_socket(self, raw_socket, *, server_hostname):
        assert server_hostname == "redis.example"
        return self.wrapped


def assert_invalid_url(url, expected):
    try:
        RedisStateRepository(url, "weatherwatch:test")
    except ValueError as error:
        assert expected in str(error)
        assert "secret" not in str(error)
        assert url not in str(error)
    else:
        raise AssertionError(f"Invalid Redis URL was accepted: {url!r}")


def test_url_parsing_and_auth_database_contract():
    repository = RedisStateRepository(
        "rediss://runtime-user:p%40ss@redis.example:6380/12",
        "weatherwatch:test",
        timeout_seconds=4,
    )
    assert repository.host == "redis.example"
    assert repository.port == 6380
    assert repository.database == 12
    assert repository.username == "runtime-user"
    assert repository.password == "p@ss"
    assert repository.tls is True
    assert repository.timeout_seconds == 4

    assert_invalid_url("http://redis.example/0", "redis:// or rediss://")
    assert_invalid_url("redis://runtime-user@redis.example/0", "requires a password")
    assert_invalid_url("redis://redis.example/not-a-db", "numeric database")
    assert_invalid_url("redis://redis.example/0?secret=value", "unsupported")
    assert_invalid_url("redis://redis.example:99999/0", "invalid port")


def test_timeout_validation():
    for timeout in (0, -1, True, float("inf"), 31):
        try:
            RedisStateRepository(
                "redis://redis.example/0",
                "weatherwatch:test",
                timeout_seconds=timeout,
            )
        except ValueError as error:
            assert "timeout" in str(error).lower()
        else:
            raise AssertionError(f"Invalid timeout was accepted: {timeout!r}")


def test_tls_wrap_failure_closes_raw_socket():
    raw_socket = FakeSocket()
    with patch("storage.state_repository.socket.create_connection", return_value=raw_socket), patch(
        "storage.state_repository.ssl.create_default_context",
        return_value=FailingTlsContext(),
    ):
        repository = RedisStateRepository(
            "rediss://:secret@redis.example/0", "weatherwatch:test"
        )
        try:
            repository._connect()
        except ssl.SSLError:
            pass
        else:
            raise AssertionError("Synthetic TLS failure did not propagate")
    assert raw_socket.closed is True


def test_tls_socket_gets_bounded_io_timeout():
    raw_socket = FakeSocket()
    wrapped_socket = FakeSocket()
    with patch("storage.state_repository.socket.create_connection", return_value=raw_socket) as connect, patch(
        "storage.state_repository.ssl.create_default_context",
        return_value=WrappedTlsContext(wrapped_socket),
    ):
        repository = RedisStateRepository(
            "rediss://:secret@redis.example/3",
            "weatherwatch:test",
            timeout_seconds=5,
        )
        assert repository._connect() is wrapped_socket
    connect.assert_called_once_with(("redis.example", 6379), timeout=5)
    assert wrapped_socket.timeouts == [5]
    assert raw_socket.closed is False


def test_configured_health_is_offline_and_secret_safe():
    original_backend = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    original_url = os.environ.get("WEATHERWATCH_REDIS_URL")
    try:
        os.environ["WEATHERWATCH_STATE_BACKEND"] = "redis"
        os.environ["WEATHERWATCH_REDIS_URL"] = (
            "rediss://runtime-user:supersecret@redis.example:6380/4"
        )
        with patch(
            "storage.state_repository.socket.create_connection",
            side_effect=AssertionError("health must not connect"),
        ):
            status = get_state_backend_status()
        assert status == {
            "state_backend": "redis",
            "state_backend_status": "configured",
        }
        assert "supersecret" not in str(status)
        assert "rediss://" not in str(status)
    finally:
        if original_backend is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original_backend
        if original_url is None:
            os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        else:
            os.environ["WEATHERWATCH_REDIS_URL"] = original_url


def test_filesystem_default_is_redis_independent():
    original_backend = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    original_url = os.environ.get("WEATHERWATCH_REDIS_URL")
    try:
        os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        with patch(
            "storage.state_repository.socket.create_connection",
            side_effect=AssertionError("filesystem mode must not connect"),
        ):
            repository = get_state_repository(
                Path("state/synthetic.json"), state_key="synthetic"
            )
            assert repository.__class__.__name__ == "JsonStateRepository"
            assert get_state_backend_status()["state_backend_status"] == "ready"
    finally:
        if original_backend is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original_backend
        if original_url is None:
            os.environ.pop("WEATHERWATCH_REDIS_URL", None)
        else:
            os.environ["WEATHERWATCH_REDIS_URL"] = original_url


def test_runtime_root_preserves_local_defaults_and_rejects_unsafe_paths():
    original_root = os.environ.get("WEATHERWATCH_RUNTIME_ROOT")
    try:
        os.environ.pop("WEATHERWATCH_RUNTIME_ROOT", None)
        assert runtime_path("state/approval_state.json") == Path(
            "state/approval_state.json"
        )

        os.environ["WEATHERWATCH_RUNTIME_ROOT"] = "/var/weatherwatch"
        assert runtime_path("output/manual_inputs") == Path(
            "/var/weatherwatch/output/manual_inputs"
        )

        for value in ("/absolute/path", "../escape", "state/../../escape", ""):
            try:
                runtime_path(value)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Unsafe runtime path was accepted: {value!r}")

        os.environ["WEATHERWATCH_RUNTIME_ROOT"] = "relative-root"
        try:
            runtime_path("state/approval_state.json")
        except ValueError as error:
            assert "absolute" in str(error)
        else:
            raise AssertionError("Relative runtime root was accepted")
    finally:
        if original_root is None:
            os.environ.pop("WEATHERWATCH_RUNTIME_ROOT", None)
        else:
            os.environ["WEATHERWATCH_RUNTIME_ROOT"] = original_root


def test_filesystem_health_rejects_unusable_runtime_root():
    original_backend = os.environ.get("WEATHERWATCH_STATE_BACKEND")
    original_root = os.environ.get("WEATHERWATCH_RUNTIME_ROOT")
    try:
        os.environ["WEATHERWATCH_STATE_BACKEND"] = "filesystem"
        with tempfile.TemporaryDirectory() as directory:
            not_a_directory = Path(directory) / "runtime-root-file"
            not_a_directory.write_text("synthetic", encoding="utf-8")
            os.environ["WEATHERWATCH_RUNTIME_ROOT"] = str(not_a_directory)
            status = get_state_backend_status()
        assert status == {
            "state_backend": "filesystem",
            "state_backend_status": "degraded",
            "state_backend_error": "Filesystem state path is not writable.",
        }
        assert str(not_a_directory) not in str(status)
    finally:
        if original_backend is None:
            os.environ.pop("WEATHERWATCH_STATE_BACKEND", None)
        else:
            os.environ["WEATHERWATCH_STATE_BACKEND"] = original_backend
        if original_root is None:
            os.environ.pop("WEATHERWATCH_RUNTIME_ROOT", None)
        else:
            os.environ["WEATHERWATCH_RUNTIME_ROOT"] = original_root


def test_facebook_token_read_modify_write_is_single_process_atomic():
    class ConcurrentProbeRepository:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.state = facebook_token_store.default_state()
            self.lock = threading.Lock()

        def _enter(self):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.01)

        def _exit(self):
            with self.lock:
                self.active -= 1

        def load(self, default_factory):
            self._enter()
            try:
                return dict(self.state)
            finally:
                self._exit()

        def save(self, state):
            self._enter()
            try:
                self.state = dict(state)
            finally:
                self._exit()

    repository = ConcurrentProbeRepository()
    with patch(
        "storage.facebook_token_store.get_state_repository",
        return_value=repository,
    ):
        first = threading.Thread(
            target=facebook_token_store.update_token_health,
            args=("ready",),
        )
        second = threading.Thread(
            target=facebook_token_store.save_page_token,
            args=("page-1", "Synthetic", "synthetic-token"),
        )
        first.start()
        second.start()
        first.join(timeout=2)
        second.join(timeout=2)
        assert not first.is_alive() and not second.is_alive()
    assert repository.max_active == 1


def main():
    test_url_parsing_and_auth_database_contract()
    test_timeout_validation()
    test_tls_wrap_failure_closes_raw_socket()
    test_tls_socket_gets_bounded_io_timeout()
    test_configured_health_is_offline_and_secret_safe()
    test_filesystem_default_is_redis_independent()
    test_runtime_root_preserves_local_defaults_and_rejects_unsafe_paths()
    test_filesystem_health_rejects_unusable_runtime_root()
    test_facebook_token_read_modify_write_is_single_process_atomic()
    print("redis runtime readiness verification ok")


if __name__ == "__main__":
    main()
