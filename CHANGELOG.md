# Changelog

All notable changes to WeatherWatch are documented here.

---

# v0.7.7 — Configurable Image Rendering

## Added

* Configurable manual image rendering modes:

  * `stretch`
  * `smartfit`
  * `crop`
* Persistent rendering configuration.
* Runtime image rendering configuration.
* `/image_fit` Telegram command.
* `/image_manual` documentation.
* SmartFit renderer preserving aspect ratio with centered crop.
* Rendering verification for multiple image aspect ratios.

## Changed

* Manual Telegram image uploads now use configurable rendering behavior.
* Automatic weather screenshots remain unchanged.

---

# v0.7.6 — ZIP VPS Deployment Package

## Added

* ZIP release builder.
* Ubuntu VPS installer.
* Installation verification script.
* systemd service template.
* VERSION file.
* Deployment documentation.
* Production verification workflow.
* Background service entrypoint.
* Release packaging.

## Improved

* Private repository deployment workflow.
* Runtime directory initialization.
* Production deployment process.

---

# v0.7.5 — Local Administration Dashboard

## Added

* Local admin dashboard.
* `/admin` endpoint.
* `/health` endpoint.
* Dashboard auto-refresh.
* Runtime health reporting.
* Safe operational summaries.
* SSH tunnel deployment documentation.

---

# v0.7.4 — Template Safety & Production Guardrails

## Added

* Editable PAGASA caption templates.
* Runtime template reload.
* Template upload.
* Template validation.
* Placeholder validation.
* Template backup retention.
* Last-known-good template protection.
* Runtime template configuration.

## Improved

* Safer template deployment.
* State persistence.
* Manual input cleanup.

---

# v0.7.3 — Structured Forecast Processing

## Added

* Structured PAGASA parser.
* Forecast extraction service.
* Forecast metadata.
* Cyclone movement parsing.
* Wind intensity parsing.
* Structured weather system extraction.
* Structured affected area extraction.

## Improved

* Facebook captions now include structured weather details.
* Caption generation now uses parsed forecast data.

---

# v0.7.2 — Facebook Publishing

## Added

* Facebook publishing.
* Approval workflow.
* Token persistence.
* Token recovery.
* Publishing safeguards.

---

# v0.7.1 — Telegram Approval Workflow

## Added

* Telegram bot integration.
* Approval workflow.
* Reject workflow.
* Manual publishing bypass.
* Administrative commands.

---

# v0.7.0 — Provider Architecture

## Added

* Provider abstraction layer.
* Provider registry.
* Provider metadata.
* Provider configuration.
* Provider switching.

## Improved

* Weather providers now operate through a unified interface.

---

# v0.6.x — Rendering Foundation

* Automated image rendering.
* Branding engine.
* Dynamic headlines.
* Adaptive typography.
* Rendering pipeline improvements.

---

# v0.5.x — Browser Automation

* Playwright integration.
* Screenshot capture.
* Browser session management.
* Capture automation.

---

# v0.4.x — Project Foundation

* Repository structure.
* Configuration management.
* Virtual environment.
* Git workflow.
* Core WeatherWatch architecture.
* Initial service layout.

---

# Future

## v0.8.x

* Production VPS deployment
* Production validation
* Monitoring improvements
* Operational hardening

## v1.0.0

First Production Release.
