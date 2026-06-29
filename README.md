# 🌤 WeatherWatch

> **A production-oriented, modular weather automation platform for the Philippines.**

WeatherWatch is an automation platform designed to collect weather information, generate branded graphics, create editable captions, provide a human approval workflow through Telegram, and publish directly to Facebook.

Rather than being a simple weather bot, WeatherWatch is designed as a production-ready system with modular architecture, runtime configuration, deployment tooling, and extensibility for future services under **Project Freedom**.

---

# 🚧 Project Status

**Version**

`v0.8.7`

**Status**

🟡 Production Candidate

Current focus:

* Configurable Image Rendering
* VPS Production Deployment
* Production Validation

Target milestone:

🎯 **v1.0.0 — First Production Release**

---

# ✨ Features

## Weather Processing

* Multi-provider weather architecture
* Structured PAGASA forecast parser
* Provider abstraction layer
* Modular forecast services

## Image Rendering

* Automated weather graphics
* Manual image rendering
* Editable templates
* Dynamic branding
* Smart rendering pipeline
* Config-driven Windy satellite, radar, wind, rain, cloud, and temperature layers

## Caption System

* Editable caption templates
* Structured forecast integration
* Runtime template reload
* Template validation
* Upload guardrails

## Publishing

* Telegram approval workflow
* Human editorial review
* Facebook publishing
* Human-selected image or native Facebook text posts
* Intent-based `/approve` and `/text_approve` workflows
* Token recovery
* State persistence

## Operations

* Local admin dashboard
* Runtime configuration
* ZIP release packaging
* VPS deployment tools
* Verification scripts

---

# 🏗 Architecture

WeatherWatch follows a modular service architecture.

```
config/
core/
services/
storage/
templates/
pipelines/
plugins/
scripts/
deploy/
docs/
tests/
state/
dist/
```

For the complete system architecture, see:

```
ARCHITECTURE.md
```

---

# 🔄 Current Workflow

```
Weather Provider

        │
        ▼

Forecast Parser

        │
        ▼

Structured Forecast

        │
        ▼

Caption Templates

        │
        ▼

Image Renderer

        │
        ▼

Telegram Approval

        │
        ▼

Human Review

        │
        ▼

Facebook Publishing

        │
        ▼

Admin Dashboard
```

---

# 📂 Project Structure

| Folder    | Purpose                       |
| --------- | ----------------------------- |
| config    | Runtime configuration         |
| core      | Application orchestration     |
| deploy    | Production deployment files   |
| dist      | Release packages              |
| docs      | Documentation                 |
| helpers   | Shared utilities              |
| output    | Generated outputs             |
| pipelines | Processing pipelines          |
| plugins   | Provider extensions           |
| scripts   | Build & deployment scripts    |
| services  | Business logic                |
| state     | Runtime state                 |
| storage   | Persistence layer             |
| templates | Caption & rendering templates |
| tests     | Verification & testing        |

---

# 📚 Documentation

| File                   | Description             |
| ---------------------- | ----------------------- |
| README.md              | Project overview        |
| ARCHITECTURE.md        | System architecture     |
| ROADMAP.md             | Development roadmap     |
| CHANGELOG.md           | Version history         |
| VERSION                | Current project version |
| docs/VPS_DEPLOYMENT.md | VPS deployment guide    |
| docs/FEATURES_AND_EXTENSION_GUIDE.md | Complete feature and extension reference |

---

# ⚙ Deployment

WeatherWatch supports ZIP-based deployment for Ubuntu VPS.

Current deployment includes:

* Ubuntu installer
* Python virtual environment setup
* Runtime folder creation
* systemd service
* Verification scripts
* Local dashboard
* Health endpoint

See:

```
docs/VPS_DEPLOYMENT.md
```

---

# 💡 Development Philosophy

WeatherWatch is built around a modular architecture.

Core principles:

* Separation of concerns
* Runtime configurability
* Production readiness
* Human-in-the-loop publishing
* Incremental development
* Minimal coupling
* High cohesion
* Reusable services

Every feature should improve the platform without tightly coupling unrelated systems.

---

# 🛣 Roadmap

## Current Sprint

### v0.7.7

* Configurable Image Rendering
* SmartFit rendering
* Crop rendering
* Stretch rendering
* Runtime image configuration
* Telegram image commands

---

## Next Milestones

### v0.8.x

* Production VPS deployment
* Production validation
* Deployment monitoring
* Operational hardening

---

### v1.0.0

**First Production Release**

Requirements:

* Stable VPS deployment
* Telegram validation
* Facebook publishing validation
* Dashboard validation
* Recovery testing
* Backup verification
* Production monitoring

---

# 🔮 Future

Planned platform expansion:

* Multi-page deployment
* Additional weather providers
* REST API
* Project Freedom Dashboard
* Broadcast Stack integration
* Automation workers
* Plugin ecosystem
* Multi-service orchestration

---

# 🚀 Continue Development

WeatherWatch is under active development.

Current milestone:

**v0.7.7 — Configurable Image Rendering**

Upcoming milestones:

* VPS Production Deployment
* Production Validation
* v1.0.0 First Production Release

Long-term roadmap:

WeatherWatch → Broadcast Stack → Project Freedom Platform

Development continues in:

```
ROADMAP.md
```
