# 🛡️ Architectural Rules & Guardrails

1. **Single Source of Truth**: This repository (`alaskaintel-json`) is the **ONLY** repository allowed to run signal-fetching workflows within the AlaskaIntel ecosystem.
2. **Locked Folder Set**: No top-level folders other than the following are permitted. Any new directories must be reviewed and documented in the README:
    - `.github/` (Automated Workflows)
    - `data/` (Latest JSON Signal Outputs)
    - `public/` (Sitemaps, Assets, and **Public Archives**)
    - `pipelines/` (Core Python Scrapers and Orchestration)
    - `schemas/` (JSON Logical Shape Definitions)
    - `docs/` (Strategic Manuals and Roadmap)
3. **Naming Standards**: All scraper scripts must reside in the `pipelines/` directory and follow the `fetch_*.py` naming convention for discoverability.
4. **Environment Isolation**: No production environment variables or secrets should be housed in untracked local files. All pipeline authentication must use GitHub Secrets.
5. **Branch Baseline**: The **`master`** branch is the primary production baseline. No divergent branches (e.g., `main`, `dev`) or alternative folder structures are allowed for signal ingestion.

---

*Enforced by AlaskaIntel Operations Guardrails.*
