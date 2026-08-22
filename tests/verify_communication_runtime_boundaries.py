import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.telegram_listener as listener
import services.facebook_admin_service as facebook_admin
import services.facebook_service as facebook
import services.telegram_service as telegram


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class FakeIdentity:
    def __init__(self, identifier):
        self.id = identifier


class FakeUpdate:
    def __init__(self, chat_id, user_id):
        self.effective_message = FakeMessage()
        self.message = self.effective_message
        self.effective_chat = FakeIdentity(chat_id)
        self.effective_user = FakeIdentity(user_id)
        self.effective_message.chat = self.effective_chat
        self.effective_message.from_user = self.effective_user


class FakeApplication:
    def __init__(self):
        self.handlers = []

    @classmethod
    def builder(cls):
        app = cls()

        class Builder:
            def token(self, value):
                self.value = value
                return self

            def build(self):
                return app

        return Builder()

    def add_handler(self, handler):
        self.handlers.append(handler)


class FakeResponse:
    ok = False
    status_code = 502
    text = "access_token=SHOULD_NOT_ESCAPE"


def verify_telegram_configuration_and_errors():
    keys = (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_ALLOWED_CHAT_IDS",
        "TELEGRAM_ALLOWED_USER_IDS",
    )
    original_env = {key: os.environ.get(key) for key in keys}
    original_post = telegram.requests.post
    try:
        os.environ["TELEGRAM_BOT_TOKEN"] = "synthetic-secret-token"
        os.environ["TELEGRAM_CHAT_ID"] = "1001"
        os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = "1001,1002"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "2001"
        assert telegram.get_telegram_config() == (
            "synthetic-secret-token",
            "1001",
        )

        os.environ["TELEGRAM_CHAT_ID"] = "9999"
        try:
            telegram.get_telegram_config()
        except ValueError as error:
            assert "TELEGRAM_ALLOWED_CHAT_IDS" in str(error)
        else:
            raise AssertionError("Unauthorized outbound Telegram chat was accepted")

        os.environ["TELEGRAM_CHAT_ID"] = "1001"
        telegram.requests.post = lambda *args, **kwargs: FakeResponse()
        try:
            telegram.send_telegram_message("synthetic")
        except RuntimeError as error:
            assert str(error) == "Telegram request failed: HTTP 502"
            assert "SHOULD_NOT_ESCAPE" not in str(error)
            assert "synthetic-secret-token" not in str(error)
        else:
            raise AssertionError("Telegram HTTP failure was accepted")

        def raise_network_error(url, **kwargs):
            raise requests.ConnectionError(f"failed URL {url}")

        telegram.requests.post = raise_network_error
        try:
            telegram.send_telegram_message("synthetic")
        except RuntimeError as error:
            assert str(error) == "Telegram request failed: ConnectionError"
            assert "synthetic-secret-token" not in str(error)
        else:
            raise AssertionError("Telegram network failure was accepted")
    finally:
        telegram.requests.post = original_post
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


async def verify_telegram_command_authorization():
    original_application = listener.Application
    original_command_handler = listener.CommandHandler
    original_message_handler = listener.MessageHandler
    original_env = {
        key: os.environ.get(key)
        for key in (
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_ALLOWED_CHAT_IDS",
            "TELEGRAM_ALLOWED_USER_IDS",
        )
    }
    try:
        os.environ["TELEGRAM_BOT_TOKEN"] = "synthetic-token"
        os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = "1001"
        os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "2001"
        listener.Application = FakeApplication
        listener.CommandHandler = lambda command, callback: (
            "command",
            command,
            callback,
        )
        listener.MessageHandler = lambda filters, callback: (
            "message",
            callback,
        )
        app = listener.build_telegram_app()
        commands = {
            item[1]: item[2]
            for item in app.handlers
            if item[0] == "command"
        }

        for command in ("start", "status", "ai_status", "memory_status"):
            update = FakeUpdate(chat_id=9999, user_id=9999)
            await commands[command](update, object())
            assert update.message.replies == [listener.UNAUTHORIZED_MESSAGE]

        authorized = FakeUpdate(chat_id=1001, user_id=2001)
        await commands["start"](authorized, object())
        assert authorized.message.replies == ["WeatherWatch bot is online. 🦾"]
    finally:
        listener.Application = original_application
        listener.CommandHandler = original_command_handler
        listener.MessageHandler = original_message_handler
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def verify_facebook_oauth_state_and_redaction():
    assert facebook.GRAPH_API_VERSION == "v26.0"
    keys = (
        "FACEBOOK_APP_ID",
        "FACEBOOK_APP_SECRET",
        "FACEBOOK_REDIRECT_URI",
        "FACEBOOK_PAGE_ID",
        "FACEBOOK_PAGE_ACCESS_TOKEN",
    )
    original_env = {key: os.environ.get(key) for key in keys}
    facebook._pending_oauth_states.clear()
    try:
        os.environ["FACEBOOK_APP_ID"] = "synthetic-app"
        os.environ["FACEBOOK_APP_SECRET"] = "synthetic-app-secret"
        os.environ["FACEBOOK_REDIRECT_URI"] = (
            "http://127.0.0.1:8790/admin/fb/callback"
        )
        os.environ["FACEBOOK_PAGE_ID"] = "synthetic-page"
        os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"] = "synthetic-page-token"

        login_url = facebook.build_facebook_login_url()
        state = parse_qs(urlparse(login_url).query)["state"][0]
        assert state != "weatherwatch"
        assert facebook.consume_facebook_oauth_state(state) is True
        assert facebook.consume_facebook_oauth_state(state) is False

        operator_url = facebook_admin.get_admin_connect_url()
        assert operator_url.startswith(facebook.FACEBOOK_LOGIN_URL)
        operator_state = parse_qs(urlparse(operator_url).query)["state"][0]
        assert facebook.consume_facebook_oauth_state(operator_state) is True

        expired = facebook.create_facebook_oauth_state(now=10)
        assert facebook.consume_facebook_oauth_state(expired, now=611) is False

        unsafe = RuntimeError(
            "access_token=synthetic-page-token "
            "client_secret=synthetic-app-secret code=one-time-code"
        )
        safe = facebook.safe_facebook_error(unsafe)
        assert "synthetic-page-token" not in safe
        assert "synthetic-app-secret" not in safe
        assert "one-time-code" not in safe
        assert safe.count("<hidden>") == 3
    finally:
        facebook._pending_oauth_states.clear()
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def verify_facebook_admin_callback_state():
    calls = []
    original_consume = facebook_admin.consume_facebook_oauth_state
    original_reconnect = facebook_admin.reconnect_facebook_with_code

    class Handler:
        def send_html(self, status, title, body):
            calls.append((status, title, body))

    try:
        facebook_admin.consume_facebook_oauth_state = lambda state: False
        facebook_admin.reconnect_facebook_with_code = (
            lambda code: (_ for _ in ()).throw(
                AssertionError("Reconnect called with invalid state")
            )
        )
        facebook_admin.FacebookAdminHandler.handle_callback(
            Handler(),
            urlparse("/admin/fb/callback?code=synthetic&state=invalid"),
        )
        assert calls[-1][0] == 400
        assert "Invalid or expired" in calls[-1][2]

        calls.clear()
        facebook_admin.consume_facebook_oauth_state = lambda state: state == "valid"
        facebook_admin.reconnect_facebook_with_code = lambda code: {
            "page_name": "Synthetic Page"
        }
        facebook_admin.FacebookAdminHandler.handle_callback(
            Handler(),
            urlparse("/admin/fb/callback?code=synthetic&state=valid"),
        )
        assert calls[-1][0] == 200
        assert "Synthetic Page" in calls[-1][2]
    finally:
        facebook_admin.consume_facebook_oauth_state = original_consume
        facebook_admin.reconnect_facebook_with_code = original_reconnect


def verify_facebook_publication_boundary():
    originals = {
        "get_current_job": facebook.get_current_job,
        "publish_job": facebook.publish_job,
        "mark_current_publishing": facebook.mark_current_publishing,
        "mark_current_posted": facebook.mark_current_posted,
    }
    calls = []
    try:
        facebook.get_current_job = lambda: {
            "job_id": "pending-job",
            "status": "pending",
        }
        facebook.publish_job = lambda job: calls.append("published")
        try:
            facebook.publish_current_job()
        except ValueError as error:
            assert "not approved" in str(error)
        else:
            raise AssertionError("Pending job was published")
        assert calls == []

        facebook.get_current_job = lambda: {
            "job_id": "approved-job",
            "status": "approved",
            "post_type": "text",
        }
        facebook.mark_current_publishing = lambda: calls.append("publishing")
        facebook.publish_job = lambda job: calls.append("published") or {
            "id": "synthetic-post"
        }
        facebook.mark_current_posted = (
            lambda facebook_post_id: calls.append(("posted", facebook_post_id))
        )
        result = facebook.publish_current_job()
        assert calls == [
            "publishing",
            "published",
            ("posted", "synthetic-post"),
        ]
        assert result["facebook_post_id"] == "synthetic-post"
    finally:
        for name, value in originals.items():
            setattr(facebook, name, value)


def main():
    verify_telegram_configuration_and_errors()
    asyncio.run(verify_telegram_command_authorization())
    verify_facebook_oauth_state_and_redaction()
    verify_facebook_admin_callback_state()
    verify_facebook_publication_boundary()
    print("communication runtime boundary verification ok")


if __name__ == "__main__":
    main()
