# WeatherWatch Features and Extension Guide

Version: 0.8.9
Repository audit date: 2026-06-28

This document is the code-facing reference for WeatherWatch. It explains the
runtime flow, every active feature, the responsibility of each tracked file,
and the supported way to extend the system.

File: `docs/FEATURES_AND_EXTENSION_GUIDE.md`

## 1. System Purpose

WeatherWatch:

1. Fetches the PAGASA weather synopsis.
2. Selects an enabled map provider.
3. Parses weather facts into structured data.
4. Composes public-information wording.
5. Selects a config-driven map framing decision.
6. Captures a provider screenshot.
7. Renders a branded 1080x1350 graphic.
8. Sends the graphic and caption to Telegram for approval.
9. Publishes approved content to Facebook.
10. Exposes local-only health and administration routes.

The main architecture rule is:

> Configuration decides. Services execute.

## 2. Runtime Entry Points

### `main.py`

The normal local entry point:

```bash
python main.py
```

It creates `WeatherWatchService` and starts the complete application.

### `core/service.py`

The production process entry point:

```bash
python -m core.service
```

It:

- validates required environment variables;
- removes expired manual uploads;
- builds the Telegram application;
- starts the local admin dashboard when enabled;
- starts the Facebook OAuth callback server when needed;
- starts the Asia/Manila scheduler;
- sends a Telegram startup notification;
- runs Telegram long polling with indefinite bootstrap retries;
- masks Telegram bot tokens in console error summaries;
- shuts down local HTTP servers on exit.

### `deploy/weatherwatch.service.example`

The systemd unit template for `/opt/weatherwatch`. It starts
`python -m core.service`, loads `/opt/weatherwatch/.env`, restarts after
failure, and sends logs to journald.

## 3. End-to-End Update Flow

The active automatic update flow is:

```text
Telegram /update or scheduler
  -> core.app.WeatherWatch.update()
  -> PAGASA synopsis fetch
  -> provider selection
  -> pipelines.weather_pipeline.run_weather_pipeline()
  -> structured forecast parsing
  -> config-driven language normalization
  -> content composition
  -> map-framing decision
  -> provider capture
  -> branded image composition
  -> deterministic caption generation
  -> singleton approval-state creation
  -> Telegram photo preview
```

Approval continues as:

```text
/approve
  -> status: approved
  -> status: publishing
  -> Facebook photo upload
  -> success: posted and moved to history
  -> failure: publish_failed with last_error retained
```

Only one current approval job is supported. A new automatic update is skipped
while a current job exists.

## 4. Core Orchestration

### `core/app.py`

`WeatherWatch.update()` coordinates one automatic update.

Responsibilities:

- blocks generation when a current approval job exists;
- gets enabled providers from the registry;
- fetches PAGASA synopsis text;
- builds the initial job dictionary;
- tries providers until one succeeds;
- delegates processing to the weather pipeline.

Extension notes:

- A provider must supply `name`, `display_name`, `url`, and `shorten_url`.
- Provider failures are caught so another registered provider can be tried.
- Do not put provider-specific browser logic here.

### `core/scheduler.py`

Registers APScheduler cron jobs from `config/scheduler.json`.

It:

- registers enabled jobs only;
- uses the configured IANA timezone;
- removes old jobs before refresh to prevent duplicates;
- skips configured updates while a current approval job exists;
- optionally rejects stale `pending` or `modified` jobs immediately before the
  next scheduled update;
- exposes registered jobs and next-run timestamps;
- calls the same `WeatherWatch.update()` used by `/update`.

The scheduler may be disabled globally without stopping Telegram or the
dashboard.

`pending_job_policy.auto_reject_before_next_run` controls stale approval
cleanup. Only statuses listed in `reject_statuses` are eligible; validation
limits that list to `pending` and `modified`, so approved or publishing work
cannot be discarded automatically.

### `services/scheduler_config_service.py`

Manages `config/scheduler.json`:

- schema, time, action, timezone, and duplicate-ID validation;
- safe defaults when the file is missing;
- last-known-good configuration after bad reloads;
- atomic saves;
- fixed upload and backup paths;
- 100 KB upload limit;
- latest-10 backup retention;
- status, preview, builder, reload, and replacement helpers.

Supported action: `weather_update`.

The `provider` field is stored for future provider selection. Current update
generation still uses the normal provider registry.

### `core/telegram_listener.py`

This is the Telegram command router and human approval interface.

It provides:

- sender/chat allowlist checks;
- command registration;
- current-job previews with images;
- `/modify` parsing and image replacement;
- template administration;
- content-composer administration;
- image-rendering administration;
- scheduler administration;
- Facebook token/status commands;
- approval, rejection, and retry commands.

Admin authorization uses:

- `TELEGRAM_ALLOWED_CHAT_IDS`
- optional `TELEGRAM_ALLOWED_USER_IDS`

Current command families:

| Command | Purpose |
| --- | --- |
| `/start` | Bot availability check |
| `/manual` | Main command summary |
| `/status` | Current job and preview |
| `/update` | Generate an update |
| `/approve` | Publish current job |
| `/reject` | Reject current job |
| `/retry_publish` | Retry approved or failed publishing |
| `/modify` | Replace caption, headline, image, or combinations |
| `/fbstatus` | Facebook token health without exposing token |
| `/fb_reconnect` | Facebook OAuth reconnect URL |
| `/fb_set_token` | Save a manually generated Page token |
| `/template_*` | PAGASA deterministic caption templates |
| `/composer_*` | Editable editorial composer wording |
| `/image_*` | Manual fit and automatic map framing config |
| `/language_*` | PAGASA area-phrase normalization config |

`/modify` supports:

- clean caption and derived headline;
- explicit `HEADLINE:` only;
- explicit `CAPTION:` only;
- separate headline and caption;
- photo-only replacement;
- photo plus caption/headline.

Manual uploaded photos are normalized by
`services/image_rendering_service.py`; automatic provider captures are not.

### `services/control_plane_service.py`

Owns state-changing workflows shared by Telegram and the dashboard:

- generate an update;
- approve and publish the current job;
- reject eligible jobs;
- retry approved or failed publishing;
- modify headline/caption and regenerate the GPX image when needed;
- return current status.

Allowed states are enforced centrally. A process lock serializes dashboard and
Telegram actions so they cannot mutate the singleton job simultaneously.

## 5. Weather Pipeline

### `pipelines/weather_pipeline.py`

The pipeline owns processing order:

1. Parse the raw forecast text.
2. Set content type.
3. Calculate `framing_decision`.
4. Capture the provider page.
5. Build the GPX headline.
6. Render the branded graphic.
7. Build captions.
8. persist the approval job.
9. Send the Telegram review.

Important job fields:

| Field | Meaning |
| --- | --- |
| `provider` | Internal provider identifier |
| `provider_display` | Public provider name |
| `provider_url` | Public source URL |
| `url` | Capture URL |
| `forecast_text` | Raw PAGASA synopsis |
| `forecast` | Parsed and composed forecast object |
| `framing_decision` | Selected center, zoom, pan, strategy, reason |
| `raw_output_path` | Provider screenshot |
| `final_output_path` | Branded output |
| `headline` | GPX graphic headline |
| `captions` | Telegram/Facebook/Instagram captions |

## 6. Provider Capture

### `services/capture_service.py`

This is the provider-aware capture adapter.

Current capabilities:

- resolves the URL that Playwright will open;
- applies intelligent framing to WINDY;
- leaves unsupported providers unchanged;
- delegates the actual screenshot to `helpers/browser.py`.

WINDY framing rewrites:

```text
https://www.windy.com/-Satellite-satellite?satellite,LAT,LON,ZOOM
```

Panning semantics:

- `pan_x` is added to longitude in geographic degrees;
- `pan_y` is added to latitude in geographic degrees;
- invalid or out-of-range coordinates leave the original URL unchanged.

Example:

```text
center_lat: 13.5
center_lon: 122.5
pan_x: 0
pan_y: -3

final center: 10.5, 122.5
```

### Adding PANaHON Framing

PANaHON cannot automatically reuse WINDY URL framing. Its map interface needs
its own adapter.

Recommended process:

1. Inspect whether PANaHON accepts latitude, longitude, and zoom in its URL.
2. If it does, add:

   ```python
   def apply_panahon_framing(url, framing_decision):
       ...
   ```

3. Route `provider == "panahon"` through that function in
   `resolve_capture_url()`.
4. If PANaHON requires map interactions, extend `capture_page()` with a
   provider-specific callback or add a provider capture adapter. Use
   Playwright to wait for the map, set its center/zoom, then screenshot.
5. Add URL or browser-interaction verification without changing WINDY.

Current limitation:

- PANaHON receives intelligent framing metadata in the job, but its screenshot
  remains at the provider's default map view when PANaHON is enabled.

### `helpers/browser.py`

The generic Playwright screenshot executor.

It:

- launches headless Chromium;
- creates a fixed 1080x1350 viewport;
- opens the resolved URL;
- waits for DOM content and then 10 seconds;
- saves a full viewport screenshot;
- closes the browser.

Safe extensions:

- configurable provider wait times;
- provider-specific readiness selectors;
- cookie/banner handling;
- provider interaction callbacks;
- capture retries.

Keep provider policy outside this generic helper when possible.

## 7. Provider Plugins

### `plugins/sources/registry.py`

Controls which providers are active. It copies and randomizes the enabled
provider list before each update.

Configuration at the time of this audit:

- WINDY enabled;
- PANaHON imported but commented out;
- Meteoblue imported but not enabled.

### `plugins/sources/windy.py`

Defines WINDY name, display name, satellite URL, and attribution URL.

WINDY is the only provider with an implemented map-framing adapter.

### `plugins/sources/panahon.py`

Defines PANaHON metadata. Capture works as a generic page screenshot.
Intelligent map positioning is not yet implemented.

### `plugins/sources/meteoblue.py`

Placeholder provider metadata. It lacks `display_name` and `shorten_url`, so it
must be completed before enabling it in the registry.

### Region Plugin Placeholders

- `plugins/regions/north_luzon.py`
- `plugins/regions/south_luzon.py`
- `plugins/regions/visayas.py`
- `plugins/regions/mindanao.py`

These files are empty extension placeholders. Current geographic regions live
in `config/image_rendering.json`, not these modules.

## 8. Map Framing

### `services/map_framing_service.py`

Converts structured forecast facts into an executable framing decision.

Detection priority:

1. Cyclone fields plus coordinates.
2. Structured affected-weather-system aliases.
3. LPA aliases in raw text.
4. Other configured aliases in raw text.
5. Configured default.

Strategies:

- `region`: center comes from a named configured region;
- `weather_system`: center comes from parsed coordinates.

If a weather-system strategy has no coordinates, the service uses the
configured default and records the detected situation and fallback use.

The service does not invent coordinates or landfall regions.

Decision shape:

```json
{
  "enabled": true,
  "strategy": "region",
  "center_lat": 13.5,
  "center_lon": 122.5,
  "zoom": 7,
  "pan_x": 0,
  "pan_y": -3,
  "region_id": "luzon_visayas",
  "situation_id": "monsoon_southwest",
  "reason": "Habagat affecting Luzon and Visayas"
}
```

### Map Framing Configuration

`config/image_rendering.json` contains both:

- `manual_image`: user-submitted image fit policy;
- `auto_map`: automatic provider map policy.

Situation-level zoom and pan values are authoritative for matched situations.
Region entries provide geographic centers and reusable region defaults.

Use `/image_reload` after editing the file directly.

Runtime image-fit selection uses explicit intent commands:

- `/image_fit_stretch`
- `/image_fit_smartfit`
- `/image_fit_crop`

`/image_fit` without arguments remains the status command.
`/image_fit MODE` remains temporarily available as a deprecated alias.

### Config-Driven Windy Layer Selector

`config/windy_layers.json` controls Windy layer IDs, labels, enabled state,
URL patterns, the default layer, and forecast-context suggestion rules.
Satellite remains the enabled safe default. `rotation_enabled` is reserved;
v0.8.7 does not rotate layers automatically.

`services/windy_layer_service.py` validates that each URL pattern contains
exactly `{lat}`, `{lon}`, and `{zoom}`. It preserves the last-known-good
configuration in memory, falls back safely to satellite, builds final URLs,
and rejects unknown or disabled layers.

The weather pipeline keeps map framing and layer selection separate:

1. `map_framing_service` selects center, pan, and zoom.
2. `windy_layer_service` applies pan to the center coordinates.
3. The selected layer URL pattern creates the final Windy URL.
4. `capture_service` captures the resolved URL.

Generated approval jobs retain:

```json
{
  "windy_layer": "satellite",
  "windy_layer_label": "Satellite",
  "suggested_windy_layer": "satellite",
  "windy_url": "https://www.windy.com/-Satellite-satellite?satellite,15.480,120.600,5"
}
```

Allowlisted Telegram configuration commands are `/windy_manual`,
`/windy_status`, `/windy_show`, `/windy_builder`, `/windy_validate`,
`/windy_reload`, and `/windy_upload`. `/windy_layer` displays the persistent
default, current-job selection, suggestion, and enabled layers.

Explicit Windy selection commands call shared
`control_plane_service.set_windy_layer()`:

- `/windy_layer_satellite`
- `/windy_layer_radar`
- `/windy_layer_wind`
- `/windy_layer_rain`
- `/windy_layer_clouds`
- `/windy_layer_temperature`
- `/windy_layer_rain_accumulation`
- `/windy_layer_thunderstorms`

The selected layer is saved as the default in `config/windy_layers.json` and
therefore applies to succeeding manual and scheduled updates across restarts.
`/windy_layer LAYER` remains temporarily available as a deprecated alias.

The dashboard displays current/suggested layer metadata and provides
`POST /admin/action/windy_layer` using the existing dashboard authentication.
When an editable Windy job exists, the command also updates its layer metadata.
Current-job changes are metadata-only in v0.8.7: they do not recapture or
replace an already-reviewed screenshot or graphic. The persisted selection is
applied during the next normal generation before provider capture.

`tests/verify_windy_layers.py` covers configuration validation, URL creation,
framing coordinates, suggestions, disabled layers, upload safety, job
metadata, and dashboard security.

## 9. Image Rendering

### `services/image_rendering_service.py`

Owns the complete image-rendering JSON lifecycle.

Features:

- nested config validation;
- legacy flat-config normalization;
- last-known-good runtime cache;
- atomic save;
- 100 KB upload limit;
- safe generated upload paths;
- backup retention;
- manual fit-mode updates that preserve `auto_map`;
- default configuration fallback.

Manual modes:

- `stretch`: direct resize, may distort;
- `smartfit`: cover, center, and crop without distortion;
- `crop`: centered native-pixel crop, falling back to smartfit for small input.

### `services/image_service.py`

Thin job adapter around `helpers.image.compose_weather_card()`.

### `helpers/image.py`

Creates the final branded 1080x1350 image:

- resizes the base capture;
- overlays `assets/overlays/NLWW_overlay.png`;
- wraps and auto-fits the headline;
- draws source attribution;
- saves RGB JPEG output at quality 95.

### Visual Assets

| File | Purpose |
| --- | --- |
| `assets/overlays/NLWW_overlay.png` | Main GPX overlay |
| `assets/fonts/BebasNeue-Regular.otf` | Headline font |
| `assets/fonts/Arial Narrow.ttf` | Source font |
| `assets/weatherwatch_logo.png` | Product/logo asset |

## 10. PAGASA Fetching and Parsing

### `services/pagasa_service.py`

Fetches `https://www.pagasa.dost.gov.ph/weather`, finds the `Synopsis` panel,
and returns its first paragraph. Requests use a 30-second timeout.

### `services/forecast_parser.py`

Extracts structured PAGASA facts:

- advisory time;
- cyclone classification;
- local and international names;
- location and coordinates;
- maximum sustained winds;
- gustiness;
- movement direction and speed;
- affected weather system and areas.

It also:

- builds caption-template values;
- translates configured weather-system/movement labels;
- renders deterministic cyclone and affected-system detail lines;
- falls back safely when templates cannot render.

### `services/forecast_service.py`

Builds the higher-level forecast object used by the pipeline:

- weather type;
- storm list and hashtags;
- structured parser result;
- composed content;
- deterministic caption details;
- translated bulletin lines;
- Habagat, Amihan, LPA, and thunderstorm flags.

## 11. Content Composition and Captions

### `services/language_normalization_service.py`

Normalizes parsed PAGASA `affected_areas` before content composition.

Configuration: `config/language_normalization.json`

Output forms:

- `body`: preserves direction, such as `kanlurang bahagi ng Timog Luzon`;
- `headline`: concise region name, such as `Timog Luzon`;
- `short`: compact label, normally matching headline form.

Matching is case-insensitive and collapses extra whitespace. Unknown phrases
remain unchanged. The active configuration must contain western, eastern,
northern, southern, and central variants for every required base region and
subregion.

`normalize_forecast_data()` stores body forms in `affected_areas`, plus
`affected_areas_headline`, `affected_areas_short`, and the original list. The
composer uses headline forms for headlines and body forms for summaries.

The service also provides last-known-good reload, 100 KB upload limits, safe
uploads/backups, status, preview, validation, and starter JSON.

### `services/content_composer_service.py`

Turns parsed facts into a public-information story:

- configured recurring weather-system update;
- cyclone update;
- general fallback.

It matches structured or raw PAGASA system names against configured aliases,
uses normalized headline/body area forms, preserves structured cyclone facts,
and never intentionally invents measurements. Cyclone composition has
priority, followed by configured weather systems, then the general fallback.

Configured systems in v0.8.9:

- Southwest Monsoon / Habagat;
- Northeast Monsoon / Amihan;
- Intertropical Convergence Zone / ITCZ;
- Low Pressure Area / LPA;
- Easterlies;
- Shear Line;
- Frontal System, including tail-end aliases.

Missing affected areas produce safe system wording without rendering an empty
`sa` phrase.

### `services/content_composer_config_service.py`

Manages `config/content_composer.json`:

- schema and placeholder validation;
- generalized `composer.weather_systems`;
- required category, display name, aliases, headline, and summary per system;
- case-insensitive duplicate-alias detection across systems;
- last-known-good cache;
- safe defaults;
- atomic replacement;
- upload and backup directories;
- 100 KB limit;
- maximum 10 backups;
- status, preview, builder, validation, reload, and replacement helpers.

Allowed composer placeholders:

- `display_name`
- `areas_text`
- `subject`
- `parsed_forecast_text`

Legacy files containing only `composer.monsoon.systems` remain accepted. The
service copies them into the normalized in-memory `weather_systems` shape,
adds the legacy `monsoon` category when absent, and logs a safe migration
warning. Uploading or reloading a legacy file does not crash the composer.

To add a future PAGASA system, add one unique object under
`composer.weather_systems` with:

```json
{
  "category": "category_id",
  "display_name": "Public Name",
  "aliases": ["PAGASA Name", "Short Alias"],
  "headline_template": "{display_name} Nakaaapekto sa {areas_text}",
  "summary_template": "Patuloy na nakaaapekto ang {display_name} sa {areas_text}."
}
```

No Python composer change is required when the existing placeholders and
matching model are sufficient.

### `services/content_service.py`

Builds:

- graphic headline;
- Facebook/Instagram caption;
- Telegram approval preview;
- source attribution.

Behavior includes:

- multi-storm headline;
- single-storm category and PAGASA hashtag;
- composed weather-system headline including all parsed areas;
- cyclone structured details;
- composer story preference with deterministic fallback;
- PAGASA forecast and provider map attribution.

### `services/caption_template_service.py`

Manages `config/caption_templates.pagasa.json`.

It validates:

- required top-level fields;
- required deterministic templates;
- required translation maps;
- allowed placeholders;
- 100 KB maximum size.

It retains the last known good template, creates backups, keeps the latest 10,
and supports runtime reload.

Composer configuration and caption templates are intentionally separate:

- composer config controls editorial framing and aliases;
- caption templates control deterministic technical lines.

## 12. Telegram Delivery

### `services/telegram_service.py`

Uses Telegram's HTTP Bot API directly for generated previews and service
notifications.

Features:

- HTML message sending;
- 4096-character text chunking;
- photo upload;
- 1024-character photo-caption fallback;
- separate full preview message when the caption is too long.

`core/telegram_listener.py` uses `python-telegram-bot` for incoming commands;
this service uses `requests` for outgoing job delivery.

## 13. Approval and Persistence

### `storage/approval_store.py`

Persists the singleton approval system in:

```text
state/approval_state.json
```

Statuses:

- `pending`
- `modified`
- `approved`
- `publishing`
- `publish_failed`
- `posted`
- `rejected`

Publishing failures retain the current job and `last_error` for retry.
Posted/rejected jobs move to history. History older than seven days is pruned.

Approval-state access is protected by a process-level reentrant lock so each
read-modify-write transition is serialized across Telegram, dashboard, and
scheduler threads. Saves write and flush a unique temporary file in `state/`
before atomically replacing `approval_state.json`.

Reads retry transient JSON failures. A persistently malformed state file raises
a safe state-unavailable error; it is never interpreted as an empty state or
`No current job`. The existing state file remains untouched when atomic
replacement fails.

Persisted metadata includes:

- provider/source;
- headline/captions;
- final and raw image paths;
- framing decision;
- timestamps;
- Facebook result/error fields.
- `post_type`, enabled `available_post_types`, and optional suggested type.

### `storage/file_retention.py`

Deletes manual image inputs older than seven days while protecting files used
by the current job.

### `services/approval_bot.py`

Legacy standalone approval implementation using
`output/pending_posts.json` and job-ID command arguments.

It is not used by `main.py` or `core/service.py`. New work should target
`core/telegram_listener.py` and `storage/approval_store.py`.

### Empty Service Placeholders

- `services/approval_service.py`
- `services/publish_service.py`

They currently contain no implementation and are not part of the runtime
flow.

## 14. Facebook Publishing and Tokens

### `services/facebook_service.py`

Provides:

- OAuth login URL generation;
- OAuth code exchange;
- long-lived user-token exchange;
- `/me/accounts` Page discovery;
- configured Page selection;
- Page-token validation;
- token health checks;
- manual Page-token save;
- token-store-first lookup with environment fallback;
- photo publishing;
- native text publishing through the Page feed endpoint;
- post-type dispatch without changing the photo upload implementation;
- approval-state transitions.

Caption source priority:

1. `job["captions"]["facebook"]`
2. legacy `job["caption"]`

The full token is never returned by status helpers.

### Native Text Post Publisher

`config/post_types.json` controls the default, supported, and enabled post
types. `services/post_type_config_service.py` validates this file, preserves
the last-known-good in-memory configuration, and falls back safely to image
publishing when the file is missing or invalid.

Approval jobs default to:

```json
{
  "post_type": "image",
  "available_post_types": ["image", "text"],
  "suggested_post_type": "image"
}
```

The `publish_job(job)` dispatcher uses the unchanged photo path for `image`
and the Facebook Page feed endpoint for `text`. Text posts use only the final
Facebook caption and ignore the retained image path. Retry uses the stored
`post_type`.

Authorized Telegram admins use `/post_type` to inspect the current selection,
`/post_type_image` to select image publishing, and `/post_type_text` to select
native text publishing. Changes are limited to pending, modified, or
publish-failed jobs. `/post_type TYPE` remains temporarily available as a
deprecated alias. The dashboard uses the same
`services.control_plane_service.set_post_type()` function through
`POST /admin/action/post_type`.

### Intent-Based Text Approval

The normal operator workflows are:

```text
/update
/approve
```

This publishes the default image job.

```text
/update
/text_approve
```

This expresses text intent directly. The shared control-plane operation stores
`job["post_type"] = "text"` before applying the normal approval transition and
calling the existing publish dispatcher. Telegram does not duplicate Facebook
publishing logic.

The dashboard exposes matching **Approve as Image** and **Approve as Text**
controls. `POST /admin/action/text_approve` calls the same shared
`text_approve_current_job()` operation and uses the existing dashboard
authentication rules.

`/post_type` remains available for inspection, debugging, and manual override.
Ordinary `/approve` preserves the stored post type; newly generated jobs
default to image. `/text_approve` is the recommended fast workflow for native
text-only posts. A failed publish retains the stored post type, so
`/retry_publish` retries the same image or text path.

Video is reserved in configuration but remains disabled and unsupported by
the publisher. This release does not auto-select text versus image and does
not add multi-platform text publishing.

### `storage/facebook_token_store.py`

Persists Page-token state in:

```text
state/facebook_token_state.json
```

It stores the token plus public metadata and health timestamps. The public
status function excludes `access_token`.

### `services/facebook_admin_service.py`

Runs the local OAuth routes:

- `/admin/fb/connect`
- `/admin/fb/callback`

It exchanges the callback code and saves the selected configured Page token.

## 15. Local Dashboard

### `services/admin_dashboard_service.py`

Runs a local `ThreadingHTTPServer` with monitoring and control-plane actions.

Routes:

- `/admin`: local monitoring page;
- `/health`: secret-free JSON health payload;
- Facebook OAuth routes when sharing the same host/port.
- POST `/admin/action/update`
- POST `/admin/action/approve`
- POST `/admin/action/reject`
- POST `/admin/action/retry_publish`
- POST `/admin/action/modify`
- POST `/admin/action/post_type`
- POST `/admin/action/text_approve`
- POST `/admin/action/windy_layer`
- `/admin/current-image`: current graphic preview restricted to image files under `output/`

Displayed health includes:

- app version and uptime;
- Telegram retry mode;
- current job;
- Facebook token metadata;
- caption-template status;
- state-file existence;
- framing decision;
- safe last error.

State-changing requests require `ADMIN_DASHBOARD_SECRET` when configured. The
secret may be supplied through the form or `X-WW-Admin-Secret` header and is
never returned in HTML or health JSON. Without a configured secret, POST
actions are allowed only when the dashboard bind host is loopback.

Defaults:

```text
127.0.0.1:8787
```

Use an SSH tunnel on VPS. Binding to `0.0.0.0` requires
`ADMIN_DASHBOARD_SECRET`, firewall rules, reverse-proxy protection, and HTTPS.

## 16. Configuration and Environment

### Runtime Telegram Intent Commands

Common operator choices are encoded directly in command names:

```text
/<subsystem>_<setting>_<choice>
```

Runtime commands express an immediate operational choice and call existing
shared services. They do not duplicate image-fit, Windy-layer, or post-type
business logic.

Current intent families:

- Image fit: `/image_fit_stretch`, `/image_fit_smartfit`, `/image_fit_crop`
- Windy: `/windy_layer_satellite`, `/windy_layer_radar`,
  `/windy_layer_wind`, `/windy_layer_rain`, `/windy_layer_clouds`,
  `/windy_layer_temperature`, `/windy_layer_rain_accumulation`,
  `/windy_layer_thunderstorms`
- Facebook type: `/post_type_image`, `/post_type_text`

The old `/image_fit MODE`, `/windy_layer LAYER`, and `/post_type TYPE`
syntaxes remain deprecated aliases and reply with the corresponding explicit
command.

Configuration-management commands such as `/windy_upload`, `/windy_reload`,
`/template_upload`, and `/composer_upload` keep their existing names and
behavior. Secret payload commands such as `/fb_set_token TOKEN` are not
runtime selectors and remain argument-based.

### `config/settings.py`

Loads `.env`, validates required runtime values, and parses Telegram allowlist
IDs.

Required at startup:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_ALLOWED_CHAT_IDS`
- `FACEBOOK_PAGE_ID`

Optional/feature-dependent values are documented in `.env.example`.

### `.env.example`

Documents Telegram, Facebook OAuth, Page token, OpenAI placeholder, and local
dashboard environment keys. Never put production secrets in this example.

### Runtime JSON Configuration

| File | Controls |
| --- | --- |
| `config/caption_templates.pagasa.json` | Technical caption line templates and translations |
| `config/content_composer.json` | Editorial wording and aliases |
| `config/image_rendering.json` | Manual image fit and automatic map framing |
| `config/scheduler.json` | Scheduler timezone, enabled state, and update jobs |
| `config/language_normalization.json` | PAGASA area phrase body/headline/short forms |
| `config/post_types.json` | Enabled Facebook publishing types and default selection |
| `config/windy_layers.json` | Windy layer URL patterns, defaults, and suggestions |

Telegram upload families write only to their fixed active config file and use
generated names in fixed runtime upload folders.

## 17. Scripts and Deployment

### `scripts/install_vps.sh`

Ubuntu installer that:

- installs OS packages;
- creates `.venv`;
- installs Python requirements;
- creates state/output/log/config-upload/config-backup directories;
- creates `.env` from `.env.example` only when missing;
- optionally installs the systemd unit.

### `scripts/verify_install.sh`

Reports PASS/WARN/FAIL checks for:

- project root;
- Python and virtual environment;
- requirements;
- environment file;
- runtime directories;
- template/config availability;
- compilation and verification scripts;
- systemd;
- local `/health`.

### `scripts/build_release_zip.sh`

Builds versioned release ZIPs while excluding:

- `.env`;
- Git metadata;
- virtual environment;
- state;
- generated output/logs;
- runtime uploads/backups;
- existing distributions;
- Python cache files.

### `docs/VPS_DEPLOYMENT.md`

Installation, ZIP upload, `.env`, systemd, logs, SSH dashboard tunnel,
backups, rollback, and security guidance.

## 18. Tests and Verification

| File | Coverage |
| --- | --- |
| `tests/verify_forecast_parser.py` | Cyclone names, class, winds, gustiness, movement |
| `tests/verify_content_composer.py` | Seven configured weather systems, cyclone, fallback, normalized areas, missing-area safety |
| `tests/verify_content_composer_config.py` | Generalized schema, legacy normalization, aliases, placeholders, wording, last-known-good |
| `tests/verify_template_guardrails.py` | Template schema, placeholders, retention, malformed parser input |
| `tests/verify_image_rendering.py` | Fit modes, aspect ratios, center preservation, invalid config |
| `tests/verify_map_framing.py` | Situations, coordinates, zoom, pan, fallback, legacy config, provider URL framing |
| `tests/verify_scheduler_config.py` | Scheduler schema, disabled jobs, defaults, reload, invalid uploads |
| `tests/verify_dashboard_control_plane.py` | Dashboard authorization, shared actions, modify/retry state rules, secret exposure |
| `tests/verify_language_normalization.py` | Direction/region coverage, forms, composer integration, fallback, invalid upload |
| `tests/verify_text_post_publisher.py` | Post-type config, guards, Facebook dispatch, retry, dashboard, and secret safety |
| `tests/verify_windy_layers.py` | Windy layer validation, URLs, framing, suggestions, metadata, and dashboard security |
| `tests/verify_approval_state_safety.py` | Atomic state writes, malformed reads, failed replacement, and concurrent updates |
| `tests/verify_telegram_intent_commands.py` | Explicit command maps, shared-service dispatch, aliases, and manual coverage |
| `test_forecast.py` | Manual live PAGASA fetch smoke script |

Run the local verification set:

```bash
.venv/bin/python tests/verify_forecast_parser.py
.venv/bin/python tests/verify_content_composer.py
.venv/bin/python tests/verify_content_composer_config.py
.venv/bin/python tests/verify_template_guardrails.py
.venv/bin/python tests/verify_image_rendering.py
.venv/bin/python tests/verify_map_framing.py
.venv/bin/python tests/verify_scheduler_config.py
.venv/bin/python tests/verify_dashboard_control_plane.py
.venv/bin/python tests/verify_language_normalization.py
.venv/bin/python tests/verify_text_post_publisher.py
.venv/bin/python tests/verify_windy_layers.py
.venv/bin/python tests/verify_approval_state_safety.py
.venv/bin/python tests/verify_telegram_intent_commands.py
.venv/bin/python -m compileall core services pipelines storage config tests
```

`test_forecast.py` requires network access.

## 19. Tracked File Catalog

This section accounts for the remaining tracked project files.

| File | Role |
| --- | --- |
| `README.md` | Project overview |
| `ARCHITECTURE.md` | Short directory-level architecture summary |
| `ROADMAP.md` | Planned milestones |
| `CHANGELOG.md` | Release history |
| `VERSION` | Current release number |
| `requirements.txt` | Pinned Python dependencies |
| `.gitignore` | Secret, state, output, backup, cache, and release exclusions |
| `templates/` | Reserved directory; current editable templates live under `config/` |

Runtime-only locations:

| Path | Contents |
| --- | --- |
| `state/` | Approval and Facebook token state |
| `output/` | Raw/final graphics and manual inputs |
| `data/template_*` | Template uploads/backups |
| `data/composer_*` | Composer uploads/backups |
| `data/image_rendering_*` | Image-config uploads/backups |
| `data/scheduler_*` | Scheduler-config uploads/backups |
| `data/language_*` | Language-normalization uploads/backups |
| `data/windy_*` | Windy-layer uploads/backups |
| `logs/` | Runtime logs when configured |
| `dist/` | Release ZIP files |

## 20. Known Constraints

- The approval model is a singleton current job, not a multi-job queue.
- Post type selection is manual; WeatherWatch does not infer image versus text.
- Native text publishing currently targets Facebook only; video is reserved.
- Windy layer changes on an existing job update metadata only; v0.8.7 does not recapture the graphic.
- Windy layer rotation is reserved but not active.
- PANaHON framing is not implemented.
- Meteoblue metadata is incomplete.
- Region plugin modules are placeholders.
- `services/approval_bot.py` is legacy and separate from the active workflow.
- `services/approval_service.py` and `services/publish_service.py` are empty.
- Provider capture uses a fixed 10-second wait rather than readiness detection.
- Document-caption routing explicitly supports `/composer_upload`,
  `/image_upload`, and `/scheduler_upload`; `/template_upload` still uses its older command-handler
  path and should be aligned before relying on document-caption uploads.
- Config JSON persistence is file-based and intended for one process.
- Dashboard forms use a shared secret rather than user accounts or sessions.
- `OPENAI_API_KEY` exists in `.env.example`, but the current content path is
  deterministic; no active OpenAI call is present.

## 21. Extension Checklist

Before adding a feature:

1. Put editable policy in the appropriate existing config file.
2. Put execution logic in a focused service.
3. Keep provider-specific behavior in provider/capture adapters.
4. Preserve singleton approval-state compatibility.
5. Protect admin commands with the Telegram allowlist.
6. Never log or return secrets.
7. Add safe fallback behavior.
8. Add a verification script or extend the relevant one.
9. Run all existing verification scripts.
10. Update `CHANGELOG.md`, `VERSION`, and release ZIP when releasing.
