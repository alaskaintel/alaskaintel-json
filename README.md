# ⚡ AlaskaIntel Signal Ingestion Engine (SOT)

> **SINGLE SOURCE OF TRUTH (SOT)**: This repository is the exclusive home for all automated signal-fetching workflows within the AlaskaIntel ecosystem. 

### 🕒 UPDATED TIME: Last Signal
`2026-04-03 15:50 UTC` | `07:50 AKDT` (Automated Pipeline Active)

---

## 🔒 LOCKED REPOSITORY STRUCTURE (Guardrails)

To prevent architectural drift and project instability, this repository is strictly locked to the following folder structure. **NO OTHER BRANCHES OR REDUNDANT FOLDERS SHOULD BE CREATED.**

| Folder | Purpose | Status |
| :--- | :--- | :--- |
| `.github/workflows/` | CI/CD Pipelines (Signal Fetchers) | **LOCKED** |
| `data/` | Real-time JSON Signals (Canonical) | **LOCKED** |
| `public/` | Public-facing Assets & Sitemaps | **LOCKED** |
| `pipelines/` | Core Python Scrapers & Orchestratation | **LOCKED** |
| `schemas/` | Signal Schema Definitions (Logic) | **LOCKED** |
| `docs/` | Strategic Roadmap & Technical Manuals | **LOCKED** |
| `archive/` | Historical Signal Repositories | **LOCKED** |

---

## 🏗 Operations Overview

AlaskaIntel leverages GitHub Actions to serve as an unmetered execution engine for state intelligence. The scraping workers are configured in `.github/workflows/` and output JSON into the respective data directories automatically.

### Endpoints (Edge Proxy)

| Endpoint | Description |
|---|---|
| `datagit.alaskaintel.com/latest_intel.json` | Live signals feed (~4,700 signals) |
| `datagit.alaskaintel.com/intel_summary.json` | Pipeline health & last update time |
| `datagit.alaskaintel.com/source_health.json` | Per-source feed health metrics |
| `datagit.alaskaintel.com/archive/{year}/{month}.json` | Historical signal archives |

---

Data is continuously refreshed every 15 minutes by the automated intelligence pipeline.
© AlaskaIntel — [alaskaintel.com](https://alaskaintel.com)
