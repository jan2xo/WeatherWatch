#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $1"
  exit 1
}

if [[ $# -ne 1 ]]; then
  echo "Usage: ./scripts/build_release_zip.sh v0.7.6"
  exit 1
fi

VERSION_TAG="$1"
ZIP_NAME="WeatherWatch-${VERSION_TAG}.zip"
DIST_DIR="dist"
ZIP_PATH="${DIST_DIR}/${ZIP_NAME}"

for path in requirements.txt .env.example core/service.py config/caption_templates.pagasa.json config/content_composer.json config/image_rendering.json config/scheduler.json config/language_normalization.json config/post_types.json config/windy_layers.json services/map_framing_service.py services/scheduler_config_service.py services/control_plane_service.py services/language_normalization_service.py services/post_type_config_service.py services/windy_layer_service.py tests/verify_text_post_publisher.py tests/verify_windy_layers.py tests/verify_approval_state_safety.py; do
  [[ -f "$path" ]] || fail "Run this script from the WeatherWatch project root. Missing: $path"
done

for path in scripts/install_vps.sh scripts/verify_install.sh deploy/weatherwatch.service.example docs/VPS_DEPLOYMENT.md VERSION CHANGELOG.md; do
  [[ -f "$path" ]] || fail "Release file missing: $path"
done

command -v zip >/dev/null 2>&1 || fail "zip command not found."

mkdir -p "$DIST_DIR"
rm -f "$ZIP_PATH"

zip -r "$ZIP_PATH" . \
  -x ".git/*" \
  -x ".venv/*" \
  -x "__pycache__/*" \
  -x "*/__pycache__/*" \
  -x "*.pyc" \
  -x ".env" \
  -x "state/" \
  -x "state/*" \
  -x "logs/" \
  -x "logs/*" \
  -x "output/" \
  -x "output/*" \
  -x "backups/" \
  -x "backups/*" \
  -x "dist/" \
  -x "dist/*" \
  -x "data/template_uploads/" \
  -x "data/template_uploads/*" \
  -x "data/template_backups/" \
  -x "data/template_backups/*" \
  -x "data/composer_uploads/" \
  -x "data/composer_uploads/*" \
  -x "data/composer_backups/" \
  -x "data/composer_backups/*" \
  -x "data/image_rendering_uploads/" \
  -x "data/image_rendering_uploads/*" \
  -x "data/image_rendering_backups/" \
  -x "data/image_rendering_backups/*" \
  -x "data/scheduler_uploads/" \
  -x "data/scheduler_uploads/*" \
  -x "data/scheduler_backups/" \
  -x "data/scheduler_backups/*" \
  -x "data/language_uploads/" \
  -x "data/language_uploads/*" \
  -x "data/language_backups/" \
  -x "data/language_backups/*" \
  -x "data/windy_uploads/" \
  -x "data/windy_uploads/*" \
  -x "data/windy_backups/" \
  -x "data/windy_backups/*" \
  -x ".DS_Store" \
  -x "*/.DS_Store"

echo "Release ZIP created:"
echo "  $ZIP_PATH"
