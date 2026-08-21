"""Small filesystem-backed state boundary for durable runtime state.

The repository keeps the current runtime compatible with JSON files while
isolating atomic persistence and safe reads so a future durable backend can
replace this boundary without changing approval-domain code.
"""

import json
import os
import socket
import ssl
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import unquote, urlparse


class StateRepository(ABC):
    @abstractmethod
    def load(self, default_factory):
        raise NotImplementedError

    @abstractmethod
    def save(self, state):
        raise NotImplementedError


class JsonStateRepository(StateRepository):
    def __init__(self, path, *, read_attempts=3, retry_seconds=0.02):
        self.path = Path(path)
        self.read_attempts = read_attempts
        self.retry_seconds = retry_seconds

    def load(self, default_factory):
        if not self.path.exists():
            return default_factory()

        last_error = None
        for attempt in range(self.read_attempts):
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                if not self.path.exists():
                    return default_factory()
                last_error = FileNotFoundError("State file temporarily unavailable.")
            except json.JSONDecodeError as error:
                last_error = error

            if attempt < self.read_attempts - 1:
                time.sleep(self.retry_seconds)

        raise RuntimeError(
            "State could not be read safely. The existing state file was not replaced."
        ) from last_error

    def save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(state, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())

            os.replace(temporary_path, self.path)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()


class RedisStateRepository(StateRepository):
    """Small Redis RESP client for one JSON document per stable state key."""

    def __init__(self, url, key, *, timeout_seconds=3):
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("WEATHERWATCH_REDIS_URL must be redis:// or rediss://.")
        self.host = parsed.hostname
        self.port = parsed.port or 6379
        self.database = int((parsed.path or "/0").lstrip("/") or 0)
        self.password = unquote(parsed.password) if parsed.password else None
        self.username = unquote(parsed.username) if parsed.username else None
        self.tls = parsed.scheme == "rediss"
        self.key = key
        self.timeout_seconds = timeout_seconds

    def _request(self, connection, *parts):
        payload = b"*" + str(len(parts)).encode() + b"\r\n"
        for part in parts:
            value = str(part).encode()
            payload += b"$" + str(len(value)).encode() + b"\r\n" + value + b"\r\n"
        connection.sendall(payload)
        return self._read_response(connection)

    def _connect(self):
        raw_socket = socket.create_connection(
            (self.host, self.port), timeout=self.timeout_seconds
        )
        if self.tls:
            return ssl.create_default_context().wrap_socket(
                raw_socket, server_hostname=self.host
            )
        return raw_socket

    @staticmethod
    def _read_response(connection):
        line = b""
        while not line.endswith(b"\r\n"):
            chunk = connection.recv(1)
            if not chunk:
                raise RuntimeError("External state backend closed the connection.")
            line += chunk
        prefix, value = line[:1], line[1:-2]
        if prefix == b"-":
            raise RuntimeError(
                f"External state backend error: {value.decode(errors='replace')}"
            )
        if prefix == b"$":
            size = int(value)
            if size == -1:
                return None
            body = b""
            while len(body) < size + 2:
                chunk = connection.recv(size + 2 - len(body))
                if not chunk:
                    raise RuntimeError("External state returned incomplete data.")
                body += chunk
            return body[:-2].decode()
        if prefix == b"+":
            return value.decode()
        raise RuntimeError("External state returned an unsupported response.")

    def _command(self, *parts):
        connection = self._connect()
        try:
            if self.password:
                auth = ("AUTH", self.username or "default", self.password)
                self._request(connection, *auth)
            if self.database:
                self._request(connection, "SELECT", self.database)
            return self._request(connection, *parts)
        finally:
            connection.close()

    def load(self, default_factory):
        try:
            raw = self._command("GET", self.key)
            if raw is None:
                return default_factory()
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("External state is malformed and was not replaced.") from error
        except (OSError, ValueError, RuntimeError) as error:
            raise RuntimeError(
                "External state could not be read safely. Existing state was not replaced."
            ) from error

    def save(self, state):
        try:
            self._command("SET", self.key, json.dumps(state, separators=(",", ":")))
        except (OSError, ValueError, RuntimeError) as error:
            raise RuntimeError(
                "External state could not be saved safely; existing state was not replaced."
            ) from error


STATE_BACKEND_ENV = "WEATHERWATCH_STATE_BACKEND"
REDIS_URL_ENV = "WEATHERWATCH_REDIS_URL"
STATE_NAMESPACE = "weatherwatch"


def get_state_backend_name():
    backend = os.getenv(STATE_BACKEND_ENV, "filesystem").strip().lower()
    if backend not in {"filesystem", "redis"}:
        raise ValueError(
            f"Unsupported {STATE_BACKEND_ENV}={backend!r}; use filesystem or redis."
        )
    return backend


def get_state_repository(path, *, state_key):
    backend = get_state_backend_name()
    if backend == "filesystem":
        return JsonStateRepository(path)
    url = os.getenv(REDIS_URL_ENV)
    if not url:
        raise ValueError(f"{REDIS_URL_ENV} is required when {STATE_BACKEND_ENV}=redis.")
    return RedisStateRepository(url, f"{STATE_NAMESPACE}:{state_key}")


def get_state_backend_status():
    backend = get_state_backend_name()
    if backend == "redis":
        url = os.getenv(REDIS_URL_ENV)
        if not url:
            return {
                "state_backend": "redis",
                "state_backend_status": "degraded",
                "state_backend_error": f"{REDIS_URL_ENV} is not configured.",
            }
        try:
            RedisStateRepository(url, f"{STATE_NAMESPACE}:health")
        except ValueError:
            return {
                "state_backend": "redis",
                "state_backend_status": "degraded",
                "state_backend_error": "Redis configuration is invalid.",
            }
    return {
        "state_backend": backend,
        "state_backend_status": "ready" if backend == "filesystem" else "configured",
    }
