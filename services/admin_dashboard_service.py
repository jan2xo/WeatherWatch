import html
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from config.settings import get_optional_env, get_required_env
from services.caption_template_service import get_template_status
from services.facebook_service import (
    build_facebook_login_url,
    get_facebook_status,
    reconnect_facebook_with_code,
)
from storage.approval_store import STATE_FILE as APPROVAL_STATE_FILE
from storage.approval_store import get_current_job
from storage.facebook_token_store import STATE_FILE as FACEBOOK_TOKEN_STATE_FILE


APP_VERSION = "0.7.5"
STARTED_AT = datetime.now()
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8787


def is_admin_dashboard_enabled():
    value = get_optional_env("ADMIN_DASHBOARD_ENABLED") or "true"
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_admin_dashboard_address():
    host = get_optional_env("ADMIN_DASHBOARD_HOST") or DEFAULT_DASHBOARD_HOST
    port = int(get_optional_env("ADMIN_DASHBOARD_PORT") or DEFAULT_DASHBOARD_PORT)
    return host, port


def safe_text(value, fallback=""):
    if value is None:
        return fallback

    text = str(value)

    if len(text) > 500:
        return text[:500] + "..."

    return text


def status_value(value):
    return html.escape(safe_text(value, "None"))


def get_state_file_status():
    return {
        "approval_state": APPROVAL_STATE_FILE.exists(),
        "facebook_token_state": FACEBOOK_TOKEN_STATE_FILE.exists(),
    }


def get_uptime_text():
    return format_uptime(get_uptime_seconds())


def get_uptime_seconds():
    return int((datetime.now() - STARTED_AT).total_seconds())


def format_uptime(total_seconds):
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"


def current_job_summary():
    job = get_current_job()

    if not job:
        return {
            "job_id": None,
            "status": "none",
            "provider": None,
            "last_error": None,
        }

    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "provider": job.get("provider_display") or job.get("provider"),
        "last_error": job.get("last_error"),
    }


def safe_facebook_status():
    status = get_facebook_status()
    return {
        "configured_page_id": status.get("configured_page_id"),
        "page_id": status.get("page_id"),
        "page_name": status.get("page_name"),
        "token_type": status.get("token_type"),
        "token_source": status.get("source"),
        "status": status.get("status"),
        "last_checked": status.get("last_checked"),
        "last_updated": status.get("last_updated"),
        "last_error": status.get("last_error"),
    }


def safe_template_status():
    status = get_template_status()
    return {
        "provider": status.get("provider"),
        "version": status.get("version"),
        "language": status.get("language"),
        "last_loaded": status.get("last_loaded"),
        "validation_status": status.get("validation_status"),
        "last_validation_error": status.get("last_validation_error"),
        "backup_count": status.get("backup_count"),
    }


def get_last_error(job, facebook_status, template_status):
    return (
        job.get("last_error")
        or facebook_status.get("last_error")
        or template_status.get("last_validation_error")
    )


def build_health_payload():
    job = current_job_summary()
    facebook_status = safe_facebook_status()
    template_status = safe_template_status()
    state_files = get_state_file_status()
    facebook_health = facebook_status.get("status") not in {"invalid", "missing"}
    template_health = template_status.get("validation_status") == "valid"

    return {
        "ok": bool(facebook_health and template_health),
        "app_version": APP_VERSION,
        "started_at": STARTED_AT.isoformat(timespec="seconds"),
        "uptime_seconds": get_uptime_seconds(),
        "telegram_status": {
            "mode": "polling",
            "bootstrap_retries": "indefinite",
            "process_restart": "use systemd on VPS",
        },
        "current_job_status": job.get("status"),
        "current_job_id": job.get("job_id"),
        "current_provider": job.get("provider"),
        "last_error": get_last_error(job, facebook_status, template_status),
        "facebook_status": {
            "source": facebook_status.get("token_source"),
            "status": facebook_status.get("status"),
            "page_name": facebook_status.get("page_name"),
            "configured_page_id": facebook_status.get("configured_page_id"),
            "last_checked": facebook_status.get("last_checked"),
            "last_updated": facebook_status.get("last_updated"),
            "last_error": facebook_status.get("last_error"),
        },
        "template_status": template_status,
        "state_files_exist": state_files,
    }


def table_rows(rows):
    return "".join(
        "<tr>"
        f"<th>{html.escape(label)}</th>"
        f"<td>{status_value(value)}</td>"
        "</tr>"
        for label, value in rows
    )


def dynamic_table_rows(rows):
    return "".join(
        "<tr>"
        f"<th>{html.escape(label)}</th>"
        f"<td data-field='{html.escape(field)}'>{status_value(value)}</td>"
        "</tr>"
        for label, value, field in rows
    )


def dashboard_script():
    return """<script>
  const dashboardState = {
    startedAt: null,
    lastHealth: null
  };

  function valueOrNone(value) {
    if (value === null || value === undefined || value === "") {
      return "None";
    }
    return String(value);
  }

  function setField(name, value) {
    document.querySelectorAll(`[data-field="${name}"]`).forEach((element) => {
      element.textContent = valueOrNone(value);
    });
  }

  function setConnectionStatus(text, isError) {
    const element = document.querySelector("[data-field='dashboard.connection']");
    if (!element) {
      return;
    }
    element.textContent = text;
    element.classList.toggle("disconnected", Boolean(isError));
  }

  function formatUptime(totalSeconds) {
    const seconds = Math.max(0, Math.floor(totalSeconds || 0));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;

    if (hours) {
      return `${hours}h ${minutes}m ${remainingSeconds}s`;
    }

    if (minutes) {
      return `${minutes}m ${remainingSeconds}s`;
    }

    return `${remainingSeconds}s`;
  }

  function updateLocalUptime() {
    if (!dashboardState.startedAt) {
      return;
    }

    const seconds = (Date.now() - dashboardState.startedAt.getTime()) / 1000;
    setField("app.uptime", formatUptime(seconds));
  }

  function updateLastError(message) {
    const element = document.querySelector("[data-field='last_error']");
    const wrapper = document.querySelector("[data-section='last_error']");

    if (!element || !wrapper) {
      return;
    }

    if (message) {
      element.textContent = message;
      wrapper.hidden = false;
      return;
    }

    element.textContent = "";
    wrapper.hidden = true;
  }

  async function refreshDashboard() {
    try {
      const response = await fetch("/health", { cache: "no-store" });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      dashboardState.lastHealth = data;

      if (data.started_at) {
        dashboardState.startedAt = new Date(data.started_at);
      }

      setField("app.status", data.ok ? "running" : "needs attention");
      setField("app.version", data.app_version);
      setField("telegram.mode", data.telegram_status?.mode);
      setField("telegram.bootstrap_retries", data.telegram_status?.bootstrap_retries);
      setField("telegram.process_restart", data.telegram_status?.process_restart);
      setField("job.status", data.current_job_status);
      setField("job.id", data.current_job_id);
      setField("job.provider", data.current_provider);
      setField("facebook.configured_page_id", data.facebook_status?.configured_page_id);
      setField("facebook.page_name", data.facebook_status?.page_name);
      setField("facebook.source", data.facebook_status?.source);
      setField("facebook.status", data.facebook_status?.status);
      setField("facebook.last_checked", data.facebook_status?.last_checked);
      setField("facebook.last_updated", data.facebook_status?.last_updated);
      setField("template.provider", data.template_status?.provider);
      setField("template.version", data.template_status?.version);
      setField("template.language", data.template_status?.language);
      setField("template.last_loaded", data.template_status?.last_loaded);
      setField("template.validation_status", data.template_status?.validation_status);
      setField("template.backup_count", data.template_status?.backup_count);
      setField(
        "state.approval_state",
        data.state_files_exist?.approval_state ? "exists" : "missing"
      );
      setField(
        "state.facebook_token_state",
        data.state_files_exist?.facebook_token_state ? "exists" : "missing"
      );
      updateLastError(data.last_error);

      const refreshedAt = new Date().toLocaleTimeString();
      setField("dashboard.last_refreshed", refreshedAt);
      setConnectionStatus("connected", false);
      updateLocalUptime();
    } catch (error) {
      setConnectionStatus("disconnected", true);
      updateLastError(`Dashboard refresh failed: ${error.message}`);
    }
  }

  refreshDashboard();
  setInterval(refreshDashboard, 10000);
  setInterval(updateLocalUptime, 1000);
</script>"""


def render_admin_page():
    job = current_job_summary()
    facebook_status = safe_facebook_status()
    template_status = safe_template_status()
    state_files = get_state_file_status()
    last_error = get_last_error(job, facebook_status, template_status)

    current_status = job.get("status") or "none"
    facebook_state = facebook_status.get("status") or "unknown"
    template_state = template_status.get("validation_status") or "unknown"

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WeatherWatch Admin</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f7f8;
      color: #172026;
    }}
    body {{
      margin: 0;
      padding: 32px;
    }}
    main {{
      max-width: 980px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 32px;
    }}
    .subtle {{
      margin: 0 0 24px;
      color: #5b6870;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    section {{
      background: #ffffff;
      border: 1px solid #d7e0e4;
      border-radius: 8px;
      padding: 18px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 8px 0;
      text-align: left;
      vertical-align: top;
      border-top: 1px solid #edf1f3;
      overflow-wrap: anywhere;
    }}
    th {{
      width: 42%;
      color: #5b6870;
      font-weight: 600;
    }}
    .pill {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      background: #e6f4ef;
      color: #116149;
      font-weight: 700;
      font-size: 13px;
    }}
    .error {{
      margin-top: 16px;
      padding: 14px 16px;
      border-radius: 8px;
      background: #fff1f0;
      border: 1px solid #ffc9c4;
      color: #8a1f16;
      overflow-wrap: anywhere;
    }}
    .statusbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 20px;
    }}
    .last-refresh {{
      color: #5b6870;
      font-size: 13px;
    }}
    .disconnected {{
      color: #b42318;
      font-weight: 700;
    }}
    [hidden] {{
      display: none !important;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        background: #101417;
        color: #edf3f6;
      }}
      .subtle, th {{
        color: #a4b0b8;
      }}
      section {{
        background: #171d21;
        border-color: #2b363c;
      }}
      th, td {{
        border-top-color: #263139;
      }}
      .pill {{
        background: #12382d;
        color: #9ee2c8;
      }}
      .error {{
        background: #361916;
        border-color: #71302a;
        color: #ffb6ad;
      }}
      .last-refresh {{
        color: #a4b0b8;
      }}
      .disconnected {{
        color: #ffb6ad;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>WeatherWatch Admin</h1>
    <p class="subtle">Local read-only dashboard. Bind this behind an SSH tunnel on VPS.</p>
    <div class="statusbar">
      <span class="pill">Job: <span data-field="job.status">{status_value(current_status)}</span></span>
      <span class="pill">Facebook: <span data-field="facebook.status">{status_value(facebook_state)}</span></span>
      <span class="pill">Template: <span data-field="template.validation_status">{status_value(template_state)}</span></span>
      <span class="last-refresh">
        Dashboard: <span data-field="dashboard.connection">connected</span>,
        refreshed <span data-field="dashboard.last_refreshed">on load</span>
      </span>
    </div>
    <div class="grid">
      <section>
        <h2>App</h2>
        <table>{dynamic_table_rows([
            ("Status", "running", "app.status"),
            ("Version", APP_VERSION, "app.version"),
            ("Uptime", get_uptime_text(), "app.uptime"),
        ])}</table>
      </section>
      <section>
        <h2>Current Job</h2>
        <table>{dynamic_table_rows([
            ("Job ID", job.get("job_id"), "job.id"),
            ("Status", job.get("status"), "job.status"),
            ("Provider", job.get("provider"), "job.provider"),
        ])}</table>
      </section>
      <section>
        <h2>Telegram</h2>
        <table>{dynamic_table_rows([
            ("Mode", "polling", "telegram.mode"),
            ("Bootstrap Retry", "indefinite", "telegram.bootstrap_retries"),
            ("VPS Restart", "use systemd on VPS", "telegram.process_restart"),
        ])}</table>
      </section>
      <section>
        <h2>Facebook</h2>
        <table>{dynamic_table_rows([
            ("Configured Page ID", facebook_status.get("configured_page_id"), "facebook.configured_page_id"),
            ("Page Name", facebook_status.get("page_name"), "facebook.page_name"),
            ("Token Source", facebook_status.get("token_source"), "facebook.source"),
            ("Status", facebook_status.get("status"), "facebook.status"),
            ("Last Checked", facebook_status.get("last_checked"), "facebook.last_checked"),
            ("Last Updated", facebook_status.get("last_updated"), "facebook.last_updated"),
        ])}</table>
      </section>
      <section>
        <h2>Template</h2>
        <table>{dynamic_table_rows([
            ("Provider", template_status.get("provider"), "template.provider"),
            ("Version", template_status.get("version"), "template.version"),
            ("Language", template_status.get("language"), "template.language"),
            ("Last Loaded", template_status.get("last_loaded"), "template.last_loaded"),
            ("Validation", template_status.get("validation_status"), "template.validation_status"),
            ("Backups", template_status.get("backup_count"), "template.backup_count"),
        ])}</table>
      </section>
      <section>
        <h2>State Files</h2>
        <table>{dynamic_table_rows([
            ("Approval State", "exists" if state_files["approval_state"] else "missing", "state.approval_state"),
            ("Facebook Token State", "exists" if state_files["facebook_token_state"] else "missing", "state.facebook_token_state"),
        ])}</table>
      </section>
    </div>
    <div class="error" data-section="last_error" {"hidden" if not last_error else ""}>
      <strong>Last error:</strong> <span data-field="last_error">{status_value(last_error)}</span>
    </div>
  </main>
  {dashboard_script()}
</body>
</html>"""
    return page.encode("utf-8")


def render_simple_page(title, body):
    content = (
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(safe_text(body))}</p>"
        "</body></html>"
    )
    return content.encode("utf-8")


class AdminDashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_content(self, status, content_type, content):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_html(self, status, content):
        self.send_content(status, "text/html; charset=utf-8", content)

    def send_json(self, status, payload):
        content = json.dumps(payload, indent=2).encode("utf-8")
        self.send_content(status, "application/json; charset=utf-8", content)

    def redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/admin":
            self.send_html(200, render_admin_page())
            return

        if parsed.path == "/health":
            self.send_json(200, build_health_payload())
            return

        if parsed.path == "/admin/fb/connect":
            self.redirect(build_facebook_login_url())
            return

        if parsed.path == "/admin/fb/callback":
            self.handle_facebook_callback(parsed)
            return

        self.send_html(404, render_simple_page("Not Found", "Unknown admin route."))

    def handle_facebook_callback(self, parsed):
        query = parse_qs(parsed.query)
        error = query.get("error_description") or query.get("error")

        if error:
            self.send_html(400, render_simple_page("Facebook Reconnect Failed", error[0]))
            return

        code = query.get("code", [None])[0]

        if not code:
            self.send_html(
                400,
                render_simple_page("Facebook Reconnect Failed", "Missing OAuth code."),
            )
            return

        try:
            result = reconnect_facebook_with_code(code)
        except Exception as error:
            self.send_html(
                500,
                render_simple_page(
                    "Facebook Reconnect Failed",
                    f"Could not save a Page token: {error}",
                ),
            )
            return

        page_name = result.get("page_name") or "configured Page"
        self.send_html(
            200,
            render_simple_page(
                "Facebook Reconnected",
                f"WeatherWatch can now publish to {page_name}. You may close this window.",
            ),
        )


def start_admin_dashboard_server():
    host, port = get_admin_dashboard_address()
    server = ThreadingHTTPServer((host, port), AdminDashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
