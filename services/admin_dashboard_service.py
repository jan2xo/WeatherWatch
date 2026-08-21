import html
import hmac
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from config.settings import get_optional_env, get_required_env
from services.caption_template_service import get_template_status
from services.facebook_service import (
    build_facebook_login_url,
    get_facebook_status,
    reconnect_facebook_with_code,
)
from services.scheduler_config_service import get_scheduler_status
from services.windy_layer_service import get_windy_layer_status
from services.ai_config_service import get_ai_config_status
import services.control_plane_service as control_plane
from core.scheduler import get_scheduler_runtime_status
from storage.approval_store import STATE_FILE as APPROVAL_STATE_FILE
from storage.approval_store import get_current_job
from storage.facebook_token_store import STATE_FILE as FACEBOOK_TOKEN_STATE_FILE


APP_VERSION = "0.9.0"
STARTED_AT = datetime.now()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = (PROJECT_ROOT / "output").resolve()
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8787
MAX_POST_BYTES = 1024 * 1024
ACTION_PATHS = {
    "/admin/action/update",
    "/admin/action/approve",
    "/admin/action/text_approve",
    "/admin/action/reject",
    "/admin/action/retry_publish",
    "/admin/action/modify",
    "/admin/action/post_type",
    "/admin/action/windy_layer",
}


def is_admin_dashboard_enabled():
    value = get_optional_env("ADMIN_DASHBOARD_ENABLED") or "true"
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_admin_dashboard_address():
    # Explicit dashboard settings remain authoritative. PORT is a generic
    # managed-runtime convention and keeps the dashboard usable behind a
    # platform health check without introducing a provider dependency.
    host = get_optional_env("ADMIN_DASHBOARD_HOST")
    if not host and get_optional_env("PORT"):
        host = "0.0.0.0"
    host = host or DEFAULT_DASHBOARD_HOST
    port = int(
        get_optional_env("ADMIN_DASHBOARD_PORT")
        or get_optional_env("PORT")
        or DEFAULT_DASHBOARD_PORT
    )
    return host, port


def is_loopback_host(host):
    return (host or "").strip().lower() in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


def is_admin_secret_configured():
    return bool(get_optional_env("ADMIN_DASHBOARD_SECRET"))


def dashboard_actions_enabled():
    host, _ = get_admin_dashboard_address()
    return is_admin_secret_configured() or is_loopback_host(host)


def authorize_dashboard_action(provided_secret=None, host=None):
    configured_secret = get_optional_env("ADMIN_DASHBOARD_SECRET")
    bind_host = host or get_admin_dashboard_address()[0]

    if configured_secret:
        return bool(
            provided_secret
            and hmac.compare_digest(
                str(provided_secret),
                configured_secret,
            )
        )

    return is_loopback_host(bind_host)


def dispatch_dashboard_action(path, fields=None):
    values = fields or {}

    if path == "/admin/action/update":
        return control_plane.generate_update()
    if path == "/admin/action/approve":
        return control_plane.approve_current_job()
    if path == "/admin/action/text_approve":
        return control_plane.text_approve_current_job()
    if path == "/admin/action/reject":
        return control_plane.reject_current_job()
    if path == "/admin/action/retry_publish":
        return control_plane.retry_publish()
    if path == "/admin/action/modify":
        return control_plane.modify_current_job(
            headline=values.get("headline") or None,
            caption=values.get("caption") or None,
        )
    if path == "/admin/action/post_type":
        return control_plane.set_post_type(values.get("post_type"))
    if path == "/admin/action/windy_layer":
        return control_plane.set_windy_layer(values.get("windy_layer"))

    raise ValueError("Unknown dashboard action.")


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
            "framing_decision": None,
            "headline": None,
            "facebook_caption": None,
            "image": None,
            "post_type": "image",
            "available_post_types": ["image", "text"],
            "suggested_post_type": None,
            "windy_layer": None,
            "windy_layer_label": None,
            "suggested_windy_layer": None,
            "windy_url": None,
            "requested_editorial_mode": "templated",
            "editorial_mode": "templated",
            "ai_status": "not_requested",
            "ai_provider": None,
            "ai_model": None,
            "ai_fallback_level": None,
            "ai_validation_state": "not_run",
            "editorial_provenance": None,
        }

    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "provider": job.get("provider_display") or job.get("provider"),
        "last_error": job.get("last_error"),
        "framing_decision": job.get("framing_decision"),
        "headline": job.get("headline"),
        "facebook_caption": (
            job.get("captions", {}).get("facebook")
            or job.get("caption")
        ),
        "image": job.get("image"),
        "post_type": job.get("post_type", "image"),
        "available_post_types": job.get(
            "available_post_types",
            ["image", "text"],
        ),
        "suggested_post_type": job.get("suggested_post_type"),
        "windy_layer": job.get("windy_layer"),
        "windy_layer_label": job.get("windy_layer_label"),
        "suggested_windy_layer": job.get("suggested_windy_layer"),
        "windy_url": job.get("windy_url"),
        "requested_editorial_mode": job.get("requested_editorial_mode", "templated"),
        "editorial_mode": job.get("editorial_mode", "templated"),
        "ai_status": job.get("ai_status", "not_requested"),
        "ai_provider": job.get("ai_provider"),
        "ai_model": job.get("ai_model"),
        "ai_fallback_level": job.get("ai_fallback_level"),
        "ai_validation_state": job.get("ai_validation_state", "not_run"),
        "editorial_provenance": job.get("editorial_provenance"),
    }


def get_current_image_path():
    job = get_current_job() or {}
    image_value = job.get("image")
    if not image_value:
        return None

    candidate = Path(image_value)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    candidate = candidate.resolve()

    if not candidate.is_relative_to(OUTPUT_ROOT):
        return None
    if not candidate.is_file():
        return None
    if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        return None

    return candidate


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


def safe_scheduler_status():
    status = get_scheduler_status()
    runtime = get_scheduler_runtime_status()
    return {
        "enabled": status.get("enabled"),
        "timezone": status.get("timezone"),
        "enabled_job_count": status.get("enabled_job_count"),
        "auto_reject_before_next_run": status.get(
            "auto_reject_before_next_run"
        ),
        "enabled_jobs": status.get("enabled_jobs"),
        "validation_status": status.get("validation_status"),
        "last_validation_error": status.get("last_validation_error"),
        "next_runs": runtime.get("registered_jobs"),
    }


def safe_windy_status():
    status = get_windy_layer_status()
    return {
        "validation_status": status.get("validation_status"),
        "last_validation_error": status.get("last_validation_error"),
        "default_layer": status.get("default_layer"),
        "rotation_enabled": status.get("rotation_enabled"),
        "enabled_layers": status.get("enabled_layers"),
    }


def safe_ai_config_status():
    status = get_ai_config_status()
    return {
        "config_path": status.get("config_path"),
        "mode": status.get("mode"),
        "fallback_enabled": status.get("fallback_enabled"),
        "max_attempts": status.get("max_attempts"),
        "validation_status": status.get("validation_status"),
        "last_validation_error": status.get("last_validation_error"),
        "providers": status.get("providers") or [],
    }


def get_last_error(
    job,
    facebook_status,
    template_status,
    scheduler_status,
    windy_status,
):
    return (
        job.get("last_error")
        or facebook_status.get("last_error")
        or template_status.get("last_validation_error")
        or scheduler_status.get("last_validation_error")
        or windy_status.get("last_validation_error")
    )


def build_health_payload():
    job = current_job_summary()
    facebook_status = safe_facebook_status()
    template_status = safe_template_status()
    scheduler_status = safe_scheduler_status()
    windy_status = safe_windy_status()
    ai_config_status = safe_ai_config_status()
    state_files = get_state_file_status()
    framing_decision = job.get("framing_decision") or {}
    facebook_health = facebook_status.get("status") not in {"invalid", "missing"}
    template_health = template_status.get("validation_status") == "valid"
    scheduler_health = (
        scheduler_status.get("validation_status") == "valid"
    )
    windy_health = windy_status.get("validation_status") == "valid"
    durable_state_available = state_files.get("approval_state", False) or not state_files

    return {
        "ok": bool(
            facebook_health
            and template_health
            and scheduler_health
            and windy_health
        ),
        "app_version": APP_VERSION,
        "application_alive": True,
        "durable_state": {
            "available": durable_state_available,
            "approval_state_file_present": state_files.get("approval_state", False),
        },
        "editorial_subsystem": {
            "templated_available": template_health,
            "ai_configuration": ai_config_status.get("validation_status"),
            "ai_optional": True,
        },
        "publication_subsystem": {
            "facebook_status": facebook_status.get("status"),
            "configured": facebook_health,
        },
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
        "requested_editorial_mode": job.get("requested_editorial_mode"),
        "editorial_mode": job.get("editorial_mode"),
        "ai_status": job.get("ai_status"),
        "ai_provider": job.get("ai_provider"),
        "ai_model": job.get("ai_model"),
        "ai_fallback_level": job.get("ai_fallback_level"),
        "ai_validation_state": job.get("ai_validation_state"),
        "editorial_provenance": job.get("editorial_provenance"),
        "current_image_available": get_current_image_path() is not None,
        "current_post_type": job.get("post_type"),
        "available_post_types": job.get("available_post_types"),
        "suggested_post_type": job.get("suggested_post_type"),
        "current_windy_layer": job.get("windy_layer"),
        "windy_layer_label": job.get("windy_layer_label"),
        "suggested_windy_layer": job.get("suggested_windy_layer"),
        "current_windy_url": job.get("windy_url"),
        "windy_status": windy_status,
        "ai_editorial_config": ai_config_status,
        "framing_decision": job.get("framing_decision"),
        "framing_source": framing_decision.get("source"),
        "framing_matched_region": framing_decision.get("matched_region_id"),
        "framing_matched_areas": framing_decision.get("matched_areas") or [],
        "framing_matched_regions": (
            framing_decision.get("matched_regions") or []
        ),
        "framing_parent_groups": (
            framing_decision.get("resolved_parent_groups") or []
        ),
        "framing_fallback_used": framing_decision.get("fallback_used", False),
        "framing_fallback_reason": framing_decision.get("fallback_reason"),
        "dashboard_actions_enabled": dashboard_actions_enabled(),
        "admin_secret_configured": is_admin_secret_configured(),
        "last_error": get_last_error(
            job,
            facebook_status,
            template_status,
            scheduler_status,
            windy_status,
        ),
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
        "scheduler_status": scheduler_status,
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
      setField("job.post_type", data.current_post_type);
      setField(
        "job.available_post_types",
        (data.available_post_types || []).join(", ")
      );
      setField("job.suggested_post_type", data.suggested_post_type);
      setField("job.windy_layer", data.current_windy_layer);
      setField("job.windy_layer_label", data.windy_layer_label);
      setField("job.suggested_windy_layer", data.suggested_windy_layer);
      setField("job.windy_url", data.current_windy_url);
      setField("job.framing_source", data.framing_source);
      setField("job.framing_matched_region", data.framing_matched_region);
      setField(
        "job.framing_matched_areas",
        (data.framing_matched_areas || []).join(", ")
      );
      setField(
        "job.framing_matched_regions",
        (data.framing_matched_regions || []).join(", ")
      );
      setField(
        "job.framing_parent_groups",
        (data.framing_parent_groups || []).join(", ")
      );
      setField("job.framing_fallback_used", data.framing_fallback_used);
      setField("job.framing_fallback_reason", data.framing_fallback_reason);
      setField("job.framing", JSON.stringify(data.framing_decision || null));
      const preview = document.querySelector("[data-current-image]");
      if (preview) {
        preview.hidden = !data.current_image_available;
        if (data.current_image_available) {
          preview.src = `/admin/current-image?v=${Date.now()}`;
        }
      }
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
      setField("scheduler.enabled", data.scheduler_status?.enabled);
      setField("scheduler.timezone", data.scheduler_status?.timezone);
      setField("scheduler.enabled_job_count", data.scheduler_status?.enabled_job_count);
      setField("scheduler.auto_reject", data.scheduler_status?.auto_reject_before_next_run);
      setField("scheduler.validation_status", data.scheduler_status?.validation_status);
      setField(
        "scheduler.next_runs",
        (data.scheduler_status?.next_runs || [])
          .map((job) => `${job.id}: ${job.next_run || "pending"}`)
          .join(", ") || "none"
      );
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


def render_admin_page(message=None, message_is_error=False):
    job = current_job_summary()
    facebook_status = safe_facebook_status()
    template_status = safe_template_status()
    scheduler_status = safe_scheduler_status()
    windy_status = safe_windy_status()
    ai_config_status = safe_ai_config_status()
    state_files = get_state_file_status()
    last_error = get_last_error(
        job,
        facebook_status,
        template_status,
        scheduler_status,
        windy_status,
    )

    current_status = job.get("status") or "none"
    facebook_state = facebook_status.get("status") or "unknown"
    template_state = template_status.get("validation_status") or "unknown"
    scheduler_state = scheduler_status.get("validation_status") or "unknown"
    framing_summary = (
        json.dumps(job.get("framing_decision"), ensure_ascii=True)
        if job.get("framing_decision")
        else "None"
    )
    scheduler_policy = (
        "enabled"
        if scheduler_status.get("auto_reject_before_next_run")
        else "disabled"
    )
    post_type_options = "".join(
        (
            f'<option value="{html.escape(post_type)}" '
            f'{"selected" if job.get("post_type") == post_type else ""}>'
            f'{html.escape(post_type.replace("_", " ").title())}</option>'
        )
        for post_type in job.get("available_post_types") or ["image", "text"]
    )
    windy_layer_options = "".join(
        (
            f'<option value="{html.escape(layer["id"])}" '
            f'{"selected" if job.get("windy_layer") == layer["id"] else ""}>'
            f'{html.escape(layer["label"])}</option>'
        )
        for layer in windy_status.get("enabled_layers") or []
    )
    notice_html = ""
    if message:
        notice_class = "notice error" if message_is_error else "notice"
        notice_html = (
            f'<div class="{notice_class}">{html.escape(message)}</div>'
        )

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
    .controls {{
      margin-bottom: 16px;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }}
    form {{
      margin: 0;
    }}
    label {{
      display: block;
      margin: 10px 0 5px;
      font-weight: 600;
    }}
    input, textarea, select {{
      box-sizing: border-box;
      width: 100%;
      padding: 9px;
      border: 1px solid #b8c4ca;
      border-radius: 5px;
      font: inherit;
    }}
    textarea {{
      min-height: 90px;
      resize: vertical;
    }}
    button {{
      padding: 9px 14px;
      border: 0;
      border-radius: 5px;
      background: #176b55;
      color: white;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    button.danger {{
      background: #a12b22;
    }}
    .notice {{
      margin-bottom: 16px;
      padding: 12px 14px;
      border: 1px solid #9bcdbd;
      border-radius: 6px;
      background: #eaf7f2;
      color: #174f3f;
    }}
    .image-preview {{
      display: block;
      width: min(100%, 420px);
      aspect-ratio: 4 / 5;
      object-fit: contain;
      background: #111820;
      border: 1px solid #d7e0e4;
      border-radius: 6px;
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
      input, textarea, select {{
        background: #101417;
        color: #edf3f6;
        border-color: #46545c;
      }}
      .notice {{
        background: #12382d;
        border-color: #276a55;
        color: #b7ead8;
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
    <p class="subtle">Local WeatherWatch control plane. Keep it behind an SSH tunnel on VPS.</p>
    {notice_html}
    <div class="statusbar">
      <span class="pill">Job: <span data-field="job.status">{status_value(current_status)}</span></span>
      <span class="pill">Facebook: <span data-field="facebook.status">{status_value(facebook_state)}</span></span>
      <span class="pill">Template: <span data-field="template.validation_status">{status_value(template_state)}</span></span>
      <span class="pill">Scheduler: <span data-field="scheduler.validation_status">{status_value(scheduler_state)}</span></span>
      <span class="last-refresh">
        Dashboard: <span data-field="dashboard.connection">connected</span>,
        refreshed <span data-field="dashboard.last_refreshed">on load</span>
      </span>
    </div>
    <section class="controls">
      <h2>Actions</h2>
      <div class="action-row">
        <form method="post" action="/admin/action/update">
          <input type="password" name="admin_secret" placeholder="Admin secret" autocomplete="off">
          <button type="submit">Generate Update</button>
        </form>
        <form method="post" action="/admin/action/approve">
          <input type="password" name="admin_secret" placeholder="Admin secret" autocomplete="off">
          <button type="submit">Approve as Image</button>
        </form>
        <form method="post" action="/admin/action/text_approve">
          <input type="password" name="admin_secret" placeholder="Admin secret" autocomplete="off">
          <button type="submit">Approve as Text</button>
        </form>
        <form method="post" action="/admin/action/reject">
          <input type="password" name="admin_secret" placeholder="Admin secret" autocomplete="off">
          <button class="danger" type="submit">Reject</button>
        </form>
        <form method="post" action="/admin/action/retry_publish">
          <input type="password" name="admin_secret" placeholder="Admin secret" autocomplete="off">
          <button type="submit">Retry Publish</button>
        </form>
      </div>
      <form method="post" action="/admin/action/modify">
        <label for="headline">GPX Headline</label>
        <textarea id="headline" name="headline">{html.escape(job.get("headline") or "")}</textarea>
        <label for="caption">Facebook Caption</label>
        <textarea id="caption" name="caption">{html.escape(job.get("facebook_caption") or "")}</textarea>
        <label for="modify-secret">Admin Secret</label>
        <input id="modify-secret" type="password" name="admin_secret" autocomplete="off">
        <div class="action-row" style="margin-top: 10px;">
          <button type="submit">Save Modify</button>
        </div>
      </form>
      <form method="post" action="/admin/action/post_type">
        <label for="post-type">Facebook Post Type</label>
        <select id="post-type" name="post_type">
          {post_type_options}
        </select>
        <label for="post-type-secret">Admin Secret</label>
        <input id="post-type-secret" type="password" name="admin_secret" autocomplete="off">
        <div class="action-row" style="margin-top: 10px;">
          <button type="submit">Set Post Type</button>
        </div>
      </form>
      <form method="post" action="/admin/action/windy_layer">
        <label for="windy-layer">Windy Layer</label>
        <select id="windy-layer" name="windy_layer">
          {windy_layer_options}
        </select>
        <label for="windy-layer-secret">Admin Secret</label>
        <input id="windy-layer-secret" type="password" name="admin_secret" autocomplete="off">
        <div class="action-row" style="margin-top: 10px;">
          <button type="submit">Set Windy Layer</button>
        </div>
        <p class="subtle">Updates metadata only. The current graphic is not recaptured.</p>
      </form>
    </section>
    <section class="controls">
      <h2>Current Graphic Preview</h2>
      <img
        class="image-preview"
        data-current-image
        src="/admin/current-image"
        alt="Current WeatherWatch graphic"
        {"hidden" if get_current_image_path() is None else ""}
      >
    </section>
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
            ("Requested Editorial Mode", job.get("requested_editorial_mode"), "job.requested_editorial_mode"),
            ("Editorial Mode", job.get("editorial_mode"), "job.editorial_mode"),
            ("AI Status", job.get("ai_status"), "job.ai_status"),
            ("AI Provider", job.get("ai_provider"), "job.ai_provider"),
            ("AI Model", job.get("ai_model"), "job.ai_model"),
            ("AI Validation", job.get("ai_validation_state"), "job.ai_validation_state"),
            ("Editorial Provenance", json.dumps(job.get("editorial_provenance"), ensure_ascii=True) if job.get("editorial_provenance") else None, "job.editorial_provenance"),
            ("Post Type", job.get("post_type"), "job.post_type"),
            ("Available Types", ", ".join(job.get("available_post_types") or []), "job.available_post_types"),
            ("Suggested Type", job.get("suggested_post_type"), "job.suggested_post_type"),
            ("Windy Layer", job.get("windy_layer"), "job.windy_layer"),
            ("Windy Label", job.get("windy_layer_label"), "job.windy_layer_label"),
            ("Suggested Windy Layer", job.get("suggested_windy_layer"), "job.suggested_windy_layer"),
            ("Windy URL", job.get("windy_url"), "job.windy_url"),
            ("Headline", job.get("headline"), "job.headline"),
            ("Facebook Caption", job.get("facebook_caption"), "job.caption"),
            ("Final Image", job.get("image"), "job.image"),
            (
                "Framing Source",
                (job.get("framing_decision") or {}).get("source"),
                "job.framing_source",
            ),
            (
                "Matched Region",
                (job.get("framing_decision") or {}).get("matched_region_id"),
                "job.framing_matched_region",
            ),
            (
                "Matched Areas",
                ", ".join((job.get("framing_decision") or {}).get("matched_areas") or []),
                "job.framing_matched_areas",
            ),
            (
                "Matched Regions",
                ", ".join((job.get("framing_decision") or {}).get("matched_regions") or []),
                "job.framing_matched_regions",
            ),
            (
                "Parent Groups",
                ", ".join((job.get("framing_decision") or {}).get("resolved_parent_groups") or []),
                "job.framing_parent_groups",
            ),
            (
                "Framing Fallback",
                (job.get("framing_decision") or {}).get("fallback_used"),
                "job.framing_fallback_used",
            ),
            (
                "Fallback Reason",
                (job.get("framing_decision") or {}).get("fallback_reason"),
                "job.framing_fallback_reason",
            ),
            ("Framing", framing_summary, "job.framing"),
            ("Pending Policy", scheduler_policy, "job.pending_policy"),
            ("Last Error", job.get("last_error"), "job.last_error"),
        ])}</table>
      </section>
      <section>
        <h2>AI Editorial Configuration</h2>
        <table>{dynamic_table_rows([
            ("Mode", ai_config_status.get("mode"), "ai.mode"),
            ("Validation", ai_config_status.get("validation_status"), "ai.validation"),
            ("Fallback", ai_config_status.get("fallback_enabled"), "ai.fallback"),
            ("Max Attempts", ai_config_status.get("max_attempts"), "ai.max_attempts"),
            ("Providers", json.dumps(ai_config_status.get("providers"), ensure_ascii=True), "ai.providers"),
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
        <h2>Scheduler</h2>
        <table>{dynamic_table_rows([
            ("Enabled", scheduler_status.get("enabled"), "scheduler.enabled"),
            ("Timezone", scheduler_status.get("timezone"), "scheduler.timezone"),
            ("Enabled Jobs", scheduler_status.get("enabled_job_count"), "scheduler.enabled_job_count"),
            ("Auto-Reject Pending", scheduler_status.get("auto_reject_before_next_run"), "scheduler.auto_reject"),
            ("Validation", scheduler_status.get("validation_status"), "scheduler.validation_status"),
            (
                "Next Runs",
                ", ".join(
                    f"{job.get('id')}: {job.get('next_run') or 'pending'}"
                    for job in scheduler_status.get("next_runs", [])
                ) or "none",
                "scheduler.next_runs",
            ),
        ])}</table>
      </section>
      <section>
        <h2>Windy Layers</h2>
        <table>{table_rows([
            ("Validation", windy_status.get("validation_status")),
            ("Default", windy_status.get("default_layer")),
            ("Rotation", windy_status.get("rotation_enabled")),
            (
                "Enabled",
                ", ".join(
                    layer["id"]
                    for layer in windy_status.get("enabled_layers", [])
                ) or "none",
            ),
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
        self.send_response(303)
        self.send_header("Location", url)
        self.end_headers()

    def send_current_image(self):
        image_path = get_current_image_path()
        if image_path is None:
            self.send_html(
                404,
                render_simple_page(
                    "Image Not Found",
                    "No current graphic preview is available.",
                ),
            )
            return

        content_type = (
            "image/png"
            if image_path.suffix.lower() == ".png"
            else "image/jpeg"
        )
        content = image_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def redirect_with_message(self, message, is_error=False):
        query = urlencode({
            "message": safe_text(message),
            "error": "1" if is_error else "0",
        })
        self.redirect(f"/admin?{query}")

    def read_form_fields(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid request length.")

        if content_length < 0 or content_length > MAX_POST_BYTES:
            raise ValueError("Request is too large.")

        raw_body = self.rfile.read(content_length).decode(
            "utf-8",
            errors="replace",
        )
        parsed = parse_qs(raw_body, keep_blank_values=True)
        return {
            key: values[0] if values else ""
            for key, values in parsed.items()
        }

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/admin":
            query = parse_qs(parsed.query)
            message = query.get("message", [None])[0]
            message_is_error = query.get("error", ["0"])[0] == "1"
            self.send_html(
                200,
                render_admin_page(
                    message=message,
                    message_is_error=message_is_error,
                ),
            )
            return

        if parsed.path == "/health":
            self.send_json(200, build_health_payload())
            return

        if parsed.path == "/admin/current-image":
            self.send_current_image()
            return

        if parsed.path == "/admin/fb/connect":
            self.redirect(build_facebook_login_url())
            return

        if parsed.path == "/admin/fb/callback":
            self.handle_facebook_callback(parsed)
            return

        self.send_html(404, render_simple_page("Not Found", "Unknown admin route."))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ACTION_PATHS:
            self.send_html(
                404,
                render_simple_page("Not Found", "Unknown admin action."),
            )
            return

        try:
            fields = self.read_form_fields()
        except ValueError as error:
            self.send_html(
                400,
                render_simple_page("Invalid Request", str(error)),
            )
            return

        provided_secret = (
            self.headers.get("X-WW-Admin-Secret")
            or fields.pop("admin_secret", None)
        )
        bind_host = self.server.server_address[0]
        if not authorize_dashboard_action(
            provided_secret=provided_secret,
            host=bind_host,
        ):
            self.send_html(
                403,
                render_simple_page(
                    "Forbidden",
                    "Dashboard action is not authorized.",
                ),
            )
            return

        try:
            result = dispatch_dashboard_action(parsed.path, fields)
        except Exception as error:
            self.redirect_with_message(
                f"Action failed: {safe_text(error)}",
                is_error=True,
            )
            return

        if parsed.path == "/admin/action/update":
            message = (
                "Weather update skipped because a current job exists."
                if isinstance(result, dict) and result.get("skipped")
                else "Weather update generated."
            )
        elif parsed.path == "/admin/action/approve":
            message = (
                "Current job approved and published. "
                f"Post ID: {result.get('facebook_post_id') or 'unknown'}"
            )
        elif parsed.path == "/admin/action/text_approve":
            message = (
                "Current job approved and published as text. "
                f"Post ID: {result.get('facebook_post_id') or 'unknown'}"
            )
        elif parsed.path == "/admin/action/reject":
            message = f"Job {result.get('job_id')} rejected."
        elif parsed.path == "/admin/action/retry_publish":
            message = (
                "Facebook publish retried successfully. "
                f"Post ID: {result.get('facebook_post_id') or 'unknown'}"
            )
        elif parsed.path == "/admin/action/post_type":
            message = (
                "Current job post type changed to "
                f"{result.get('post_type', 'unknown').upper()}."
            )
        elif parsed.path == "/admin/action/windy_layer":
            message = (
                "Windy default layer changed to "
                f"{result.get('windy_layer', 'unknown')}. "
                "Future updates will use it. "
                "The current graphic was not recaptured."
            )
        else:
            message = "Current job modified."

        self.redirect_with_message(message)

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
