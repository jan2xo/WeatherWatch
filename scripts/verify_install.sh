#!/usr/bin/env bash
set -uo pipefail

FAILURES=0
WARNINGS=0

pass() {
  echo "PASS: $1"
}

warn() {
  WARNINGS=$((WARNINGS + 1))
  echo "WARN: $1"
}

fail() {
  FAILURES=$((FAILURES + 1))
  echo "FAIL: $1"
}

check_file() {
  local path="$1"

  if [[ -f "$path" ]]; then
    pass "$path exists"
  else
    fail "$path is missing"
  fi
}

check_dir() {
  local path="$1"

  if [[ -d "$path" ]]; then
    pass "$path exists"
  else
    fail "$path is missing"
  fi
}

get_env_value() {
  local key="$1"

  if [[ ! -f .env ]]; then
    return 0
  fi

  grep -E "^${key}=" .env | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'"
}

check_project_root() {
  local missing=()

  for path in requirements.txt .env.example core/service.py; do
    if [[ ! -f "$path" ]]; then
      missing+=("$path")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "not running from WeatherWatch project root; missing: ${missing[*]}"
  else
    pass "running from WeatherWatch project root"
  fi
}

check_python_compile() {
  local python_bin="python3"

  if [[ -x .venv/bin/python ]]; then
    python_bin=".venv/bin/python"
  fi

  if "$python_bin" -m compileall core services storage config >/tmp/weatherwatch_compile.log 2>&1; then
    pass "Python compile check passed"
  else
    fail "Python compile check failed"
    sed -n '1,40p' /tmp/weatherwatch_compile.log
  fi
}

run_optional_test() {
  local path="$1"
  local python_bin="python3"

  if [[ -x .venv/bin/python ]]; then
    python_bin=".venv/bin/python"
  fi

  if [[ ! -f "$path" ]]; then
    warn "$path not present; skipped"
    return
  fi

  if "$python_bin" "$path" >/tmp/weatherwatch_test.log 2>&1; then
    pass "$path passed"
  else
    fail "$path failed"
    sed -n '1,80p' /tmp/weatherwatch_test.log
  fi
}

check_systemd() {
  if ! command -v systemctl >/dev/null 2>&1; then
    warn "systemctl not available; skipped service status"
    return
  fi

  if systemctl list-unit-files weatherwatch.service >/dev/null 2>&1; then
    pass "systemd service is installed"
    systemctl is-enabled weatherwatch >/dev/null 2>&1 \
      && pass "systemd service is enabled" \
      || warn "systemd service is installed but not enabled"
    systemctl is-active weatherwatch >/dev/null 2>&1 \
      && pass "systemd service is running" \
      || warn "systemd service is not running"
  else
    warn "systemd service is not installed"
  fi
}

check_health_endpoint() {
  local host
  local port

  host="$(get_env_value ADMIN_DASHBOARD_HOST)"
  port="$(get_env_value ADMIN_DASHBOARD_PORT)"

  host="${host:-127.0.0.1}"
  port="${port:-8787}"

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl not available; skipped /health check"
    return
  fi

  if curl --fail --silent --max-time 3 "http://${host}:${port}/health" >/tmp/weatherwatch_health.json 2>/dev/null; then
    pass "/health endpoint responded"
  else
    warn "/health endpoint did not respond; dashboard may not be running yet"
  fi
}

check_project_root

command -v python3 >/dev/null 2>&1 \
  && pass "python3 exists" \
  || fail "python3 is missing"

check_dir ".venv"
check_file "requirements.txt"
check_file ".env"
check_dir "state"
check_dir "output"
check_dir "logs"
check_file "config/caption_templates.pagasa.json"
check_file "config/language_normalization.json"
check_file "config/post_types.json"
check_file "config/windy_layers.json"

check_python_compile
run_optional_test "tests/verify_forecast_parser.py"
run_optional_test "tests/verify_template_guardrails.py"
run_optional_test "tests/verify_language_normalization.py"
run_optional_test "tests/verify_text_post_publisher.py"
run_optional_test "tests/verify_windy_layers.py"
run_optional_test "tests/verify_approval_state_safety.py"
check_systemd
check_health_endpoint

echo
echo "Verification summary: ${FAILURES} FAIL, ${WARNINGS} WARN"

if [[ "$FAILURES" -gt 0 ]]; then
  exit 1
fi

exit 0
