# Changelog

## v0.7.7 - Configurable Image Rendering

- Added persistent `stretch`, `smartfit`, and `crop` modes for manual Telegram image uploads.
- Added allowlisted `/image_fit` and `/image_manual` Telegram commands.
- Added safe `smartfit` fallback for missing or invalid rendering configuration.
- Added rendering verification across common mobile and desktop image aspect ratios.
- Kept automatic weather screenshots and provider captures unchanged.

## v0.7.6 - ZIP VPS Installation Package

- Added ZIP release builder for private-repo VPS deployments.
- Added Ubuntu VPS installer for Python environment setup and runtime folders.
- Added systemd service example for background WeatherWatch operation.
- Added install verification script with PASS/WARN/FAIL checks.
- Expanded VPS deployment documentation for ZIP upload, install, service use, dashboard access, backups, and rollback.
