# 🟢 MASTER SOURCE OF TRUTH: alaskaintel/alaskaintel-json

This repository ([alaskaintel/alaskaintel-json](https://github.com/alaskaintel/alaskaintel-json)) is the **Official Master Source of Truth** for the AlaskaIntel ecosystem.

## 🏗️ Role & Authority
- **Central Intelligence Hub**: All automated scrapers and data pipelines (Internal and Public) ultimately synchronize their final structured output to the `data/` directory in this repository.
- **Edge Proxy Origin**: The `datagit.alaskaintel.com` edge proxy is mapped directly to the `main` branch of this repository. 
- **Production Data Source**: All AlaskaIntel frontends (Radar, Wall, Globe, Aviation, etc.) consume the real-time signals served from this repository.

## 📊 Dataset Statistics (as of 2026-04-01)

- **Signal Count**: 4,744 active intelligence signals.
- **Data Footprint**: ~10.2 MB (JSON).
- **Date Range**:
  - **Earliest Signal**: 2020-10-23
  - **Latest Signal**: 2026-01-01 (Clean verified signals)
  - **Future Signals**: Up to 2026-04-13 (includes legislative schedules)
- **Feed Coverage**: 272 verified RSS/JSON/HTML signal sources.

## ⚙️ Core Logic
The master aggregator script ([fetch_intel.py](scripts/fetch_intel.py)) manages the normalization and injection of:

1. **RSS Feeds**: 272 sources across Safety, Government, Industry, and Environment.
2. **AST Logs**: Real-time Alaska State Trooper dispatch reports.
3. **Global Map Layers**: USGS Earthquakes, NWS Weather, and AFS Wildfire signals.
4. **Legislative Actions**: Scraped directly from akleg.gov.

## 📜 Rules for Maintenance

1. **Logic First**: Any logic improvements made in private pipelines must be merged back to this repository to ensure public signal parity.
2. **Schema Integrity**: Data must strictly adhere to the schemas in `/schemas` to prevent frontend runtime errors.
3. **Automation**: GitHub Actions are the primary drivers for daily/hourly updates. Avoid manual commits to `data/` unless performing a master synchronization.

---
*This document serves as the structural declaration for the AlaskaIntel Data Engine.*
