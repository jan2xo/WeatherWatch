import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from config.settings import get_required_env
from services.facebook_service import (
    build_facebook_login_url,
    consume_facebook_oauth_state,
    reconnect_facebook_with_code,
    safe_facebook_error,
)


def get_admin_connect_url():
    # Only the authorized Telegram command should initiate reconnect. Returning
    # the provider URL here prevents an unauthenticated local HTTP GET from
    # minting a valid callback state.
    return build_facebook_login_url()


def get_admin_server_address():
    redirect_uri = get_required_env("FACEBOOK_REDIRECT_URI")
    parsed = urlparse(redirect_uri)

    if parsed.scheme != "http":
        raise ValueError("FACEBOOK_REDIRECT_URI must use http for the local admin server.")

    if not parsed.hostname:
        raise ValueError("FACEBOOK_REDIRECT_URI must include a hostname.")

    port = parsed.port or 80
    host = parsed.hostname

    if host == "localhost":
        host = "127.0.0.1"

    return host, port


def render_page(title, body):
    return (
        "<!doctype html>"
        "<html><head>"
        "<meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(body)}</p>"
        "</body></html>"
    ).encode("utf-8")


class FacebookAdminHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_html(self, status, title, body):
        content = render_page(title, body)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/admin/fb/connect":
            self.send_html(
                403,
                "Facebook Reconnect Restricted",
                "Start Facebook reconnect from the authorized Telegram control plane.",
            )
            return

        if parsed.path == "/admin/fb/callback":
            self.handle_callback(parsed)
            return

        self.send_html(404, "Not Found", "Unknown admin route.")

    def handle_callback(self, parsed):
        query = parse_qs(parsed.query)
        state = query.get("state", [None])[0]

        if not consume_facebook_oauth_state(state):
            self.send_html(
                400,
                "Facebook Reconnect Failed",
                "Invalid or expired reconnect state. Start the reconnect flow again.",
            )
            return

        error = query.get("error_description") or query.get("error")

        if error:
            self.send_html(
                400,
                "Facebook Reconnect Failed",
                safe_facebook_error(error[0]),
            )
            return

        code = query.get("code", [None])[0]

        if not code:
            self.send_html(400, "Facebook Reconnect Failed", "Missing OAuth code.")
            return

        try:
            result = reconnect_facebook_with_code(code)
        except Exception as error:
            self.send_html(
                500,
                "Facebook Reconnect Failed",
                f"Could not save a Page token: {safe_facebook_error(error)}",
            )
            return

        page_name = result.get("page_name") or "configured Page"
        self.send_html(
            200,
            "Facebook Reconnected",
            f"WeatherWatch can now publish to {page_name}. You may close this window.",
        )


def start_facebook_admin_server():
    host, port = get_admin_server_address()
    server = ThreadingHTTPServer((host, port), FacebookAdminHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
