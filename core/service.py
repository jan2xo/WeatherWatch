import re
import signal
import threading
from urllib.parse import urlparse

from services.telegram_service import send_telegram_message
from core.telegram_listener import build_telegram_app
from core.scheduler import start_scheduler
from core.app import WeatherWatch
from config.settings import get_optional_env, validate_runtime_config
from services.admin_dashboard_service import (
    get_admin_dashboard_address,
    is_admin_dashboard_enabled,
    start_admin_dashboard_server,
)
from services.facebook_admin_service import (
    get_admin_server_address,
    start_facebook_admin_server,
)
from storage.file_retention import cleanup_manual_inputs


def same_address(left, right):
    left_host = "127.0.0.1" if left[0] == "localhost" else left[0]
    right_host = "127.0.0.1" if right[0] == "localhost" else right[0]
    return left_host == right_host and int(left[1]) == int(right[1])


def dashboard_handles_facebook_callback(server, redirect_uri):
    """HTTPS callbacks terminate at the managed dashboard/proxy endpoint."""

    parsed = urlparse(redirect_uri or "")
    return bool(
        server
        and parsed.scheme == "https"
        and parsed.path == "/admin/fb/callback"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def safe_error_summary(error):
    lines = str(error).splitlines()
    message = lines[0] if lines else error.__class__.__name__
    message = re.sub(r"/bot[^/\s]+/", "/bot<hidden>/", message)
    return f"{error.__class__.__name__}: {message}"


HTTP_SHUTDOWN_TIMEOUT_SECONDS = 2.0


def shutdown_http_server(server, label, timeout=HTTP_SHUTDOWN_TIMEOUT_SECONDS):
    """Stop an HTTPServer without allowing its internal wait to hang shutdown."""
    if server is None:
        return True

    completed = threading.Event()
    shutdown_errors = []

    def request_shutdown():
        try:
            server.shutdown()
        except Exception as error:
            shutdown_errors.append(error)
        finally:
            completed.set()

    shutdown_thread = threading.Thread(
        target=request_shutdown,
        name=f"weatherwatch-{label}-shutdown",
        daemon=True,
    )
    shutdown_thread.start()
    interrupted = False
    try:
        shutdown_thread.join(timeout=max(0.0, float(timeout)))
    except KeyboardInterrupt:
        # A repeated Ctrl-C must not strand the process inside HTTPServer's
        # internal shutdown wait. Continue with socket closure.
        interrupted = True

    stopped = completed.is_set() and not shutdown_errors and not interrupted
    if not stopped:
        if interrupted:
            print(f"{label} shutdown interrupted; closing the listening socket.")
        elif shutdown_errors:
            print(
                f"{label} shutdown failed: "
                f"{safe_error_summary(shutdown_errors[0])}"
            )
        else:
            print(f"{label} shutdown timed out; closing the listening socket.")

    try:
        server.server_close()
    except KeyboardInterrupt:
        print(f"{label} close interrupted by user.")
        stopped = False
    except Exception as error:
        print(f"{label} close failed: {safe_error_summary(error)}")
        stopped = False

    return stopped


def shutdown_scheduler(scheduler_instance):
    if scheduler_instance is None or not getattr(scheduler_instance, "running", False):
        return True

    try:
        scheduler_instance.shutdown(wait=False)
    except Exception as error:
        print(f"Scheduler shutdown failed: {safe_error_summary(error)}")
        return False

    return True


class WeatherWatchService:
    def run(self):
        print("WeatherWatch Service Started")
        print("Telegram Listener Running")
        print("Press CTRL+C to stop.")

        telegram_app = None
        scheduler_instance = None
        admin_dashboard_server = None
        facebook_admin_server = None

        dashboard_address = None
        facebook_admin_address = None

        try:
            validate_runtime_config()
            cleanup_manual_inputs()

            telegram_app = build_telegram_app()

            if is_admin_dashboard_enabled():
                try:
                    dashboard_address = get_admin_dashboard_address()
                    admin_dashboard_server = start_admin_dashboard_server()
                    admin_dashboard_server.daemon_threads = True
                    print(
                        "Admin dashboard running at "
                        f"http://{dashboard_address[0]}:{dashboard_address[1]}/admin"
                    )
                except Exception as error:
                    print(
                        "Admin dashboard not started: "
                        f"{safe_error_summary(error)}"
                    )
                    if get_optional_env("PORT"):
                        raise RuntimeError(
                            "Managed-runtime HTTP server failed to start."
                        ) from error

            facebook_redirect_uri = get_optional_env("FACEBOOK_REDIRECT_URI")
            if facebook_redirect_uri and not dashboard_handles_facebook_callback(
                admin_dashboard_server,
                facebook_redirect_uri,
            ):
                try:
                    facebook_admin_address = get_admin_server_address()
                except Exception as error:
                    print(
                        "Facebook admin reconnect server not started: "
                        f"{safe_error_summary(error)}"
                    )

                if facebook_admin_address and not (
                    admin_dashboard_server
                    and dashboard_address
                    and same_address(dashboard_address, facebook_admin_address)
                ):
                    try:
                        facebook_admin_server = start_facebook_admin_server()
                        facebook_admin_server.daemon_threads = True
                    except OSError as error:
                        print(
                            "Facebook admin reconnect server not started: "
                            f"{safe_error_summary(error)}"
                        )

            weatherwatch = WeatherWatch()

            try:
                send_telegram_message("WeatherWatch bot is online. 🦾")
            except Exception as error:
                print(f"Startup Telegram notification failed: {safe_error_summary(error)}")

            scheduler_instance = start_scheduler(weatherwatch.update)

            telegram_app.run_polling(
                bootstrap_retries=-1,
                stop_signals=(signal.SIGINT, signal.SIGTERM),
            )

        except KeyboardInterrupt:
            print("WeatherWatch Service stopped by user.")

        except Exception as error:
            summary = safe_error_summary(error)
            print(f"WeatherWatch Service crashed: {summary}")

            try:
                send_telegram_message(f"WeatherWatch bot crashed. ⚠️\n\n{summary}")
            except Exception:
                pass

            raise

        finally:
            shutdown_scheduler(scheduler_instance)
            shutdown_http_server(
                facebook_admin_server,
                "Facebook admin server",
            )
            shutdown_http_server(
                admin_dashboard_server,
                "Admin dashboard server",
            )

            print("WeatherWatch Service ended.")


if __name__ == "__main__":
    WeatherWatchService().run()
