#!/usr/bin/env bash
set -euo pipefail

INSTALL_SERVICE=false

for arg in "$@"; do
  case "$arg" in
    --install-service)
      INSTALL_SERVICE=true
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Usage: ./scripts/install_vps.sh [--install-service]"
      exit 1
      ;;
  esac
done

fail() {
  echo "FAIL: $1"
  exit 1
}

info() {
  echo "==> $1"
}

require_project_root() {
  local missing=()

  for path in requirements.txt .env.example core/service.py; do
    if [[ ! -f "$path" ]]; then
      missing+=("$path")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "Run this script from the WeatherWatch project root. Missing: ${missing[*]}"
  fi
}

install_apt_packages() {
  if ! command -v apt-get >/dev/null 2>&1; then
    fail "apt-get was not found. This installer is intended for Ubuntu VPS."
  fi

  info "Installing Ubuntu packages"
  sudo apt-get update
  sudo apt-get install -y git python3 python3-venv python3-pip curl unzip ufw
}

setup_python_env() {
  info "Creating Python virtual environment"

  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi

  info "Installing Python dependencies"
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
}

create_runtime_folders() {
  info "Creating runtime folders"
  mkdir -p \
    state \
    data \
    data/template_backups \
    data/template_uploads \
    data/composer_backups \
    data/composer_uploads \
    data/image_rendering_backups \
    data/image_rendering_uploads \
    data/scheduler_backups \
    data/scheduler_uploads \
    output \
    logs \
    backups
}

setup_env_file() {
  if [[ ! -f .env ]]; then
    info "Creating .env from .env.example"
    cp .env.example .env
  else
    info ".env already exists; leaving it untouched"
  fi

  chmod 600 .env
}

install_systemd_service() {
  local template="deploy/weatherwatch.service.example"
  local target="/etc/systemd/system/weatherwatch.service"
  local user_name

  if [[ ! -f "$template" ]]; then
    fail "Missing service template: $template"
  fi

  if [[ "$(pwd)" != "/opt/weatherwatch" ]]; then
    echo "WARN: systemd template uses /opt/weatherwatch."
    echo "WARN: Current directory is $(pwd). Install from /opt/weatherwatch for production."
  fi

  user_name="$(id -un)"

  info "Installing systemd service"
  sed "s/USER_REPLACE_ME/${user_name}/g" "$template" | sudo tee "$target" >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable weatherwatch

  echo
  echo "Service installed but not started."
  echo "Next command:"
  echo "  sudo systemctl start weatherwatch"
}

print_final_checklist() {
  cat <<'EOF'

WeatherWatch VPS install completed.

Final checklist:
  1. Edit .env and add real secrets:
     nano .env
  2. Verify install:
     ./scripts/verify_install.sh
  3. Start service if installed:
     sudo systemctl start weatherwatch
  4. Watch logs:
     journalctl -u weatherwatch -f
  5. Access dashboard through SSH tunnel:
     ssh -L 8787:127.0.0.1:8787 user@server
     http://127.0.0.1:8787/admin

EOF
}

require_project_root
install_apt_packages
setup_python_env
create_runtime_folders
setup_env_file

if [[ "$INSTALL_SERVICE" == "true" ]]; then
  install_systemd_service
fi

print_final_checklist
