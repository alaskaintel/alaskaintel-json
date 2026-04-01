# 🚀 AlaskaIntel Serverless Data Engine & Static API (`intel-json`)

Welcome to the **AlaskaIntel Data Engine**. This repository is the public, serverless, automated beating heart of the AlaskaIntel ecosystem. It powers the frontend components of `radar.alaskaintel.com`, `wall.alaskaintel.com`, `globe.alaskaintel.com`, `aviation.alaskaintel.com`, and other public facing tools.

> [!CAUTION]
> **THIS IS A PUBLIC REPOSITORY.**
> Anything pushed here is immediately visible to the entire world and instantly cached by CDN networks. Read and strictly adhere to `RULES.md` before pushing any code or data.

---

## 🏗️ Architecture & Purpose

This repository is designed to completely eliminate the need for costly dynamic web servers or complicated database queries for public-facing data. 

Because this repository is public, we take full advantage of **free GitHub Actions minutes** and **free GitHub raw CDN delivery**.

### 1. The GitHub Actions Pipeline Engine
We use GitHub Actions to run scheduled web-scrapers, NLP text extractors, and data aggregation pipelines (mostly Python and Node scripts).
- Actions are scheduled using `cron` syntax.
- They fetch messy data from external government servers (e.g. DPS, ADF&G, NOAA, NamUs).
- They normalize, structure, and minify the data.
- **They commit the resulting `.json` files directly back to this repository.**

### 2. The Static JSON API (Free CDN)
Once the GitHub Action commits the `.json` data to the `main` branch, we serve those files to our React/Vue/Astro frontend applications.
- We bypass standard servers entirely.
- By fetching from `https://raw.githubusercontent.com/alaskaintel/intel-json/main/data/...`, we achieve blazingly fast global delivery at $0 infrastructure cost.

---

## 📊 Active Signal Feeds (Snapshot)

This table tracks the current volume of live intelligence sources stored in the static JSON engine. 

| Source Node | Type | Total Signals | Last Pulled (Local) |
|---|---|---|---|
| `afs_fires.json` | Array | **15** | 2026-04-01 09:47:45 |
| `ak_school_districts.json` | Array | **54** | 2026-04-01 08:57:13 |
| `ak_schools.json` | Array | **731** | 2026-04-01 08:57:13 |
| `aviation.json` | Object | **5** | 2026-04-01 09:47:45 |
| `earthquakes.json` | Object | **6** | 2026-04-01 09:47:45 |
| `k12_districts.json` | Array | **1,095** | 2026-04-01 08:57:13 |
| `legislature.json` | Object | **7** | 2026-04-01 08:57:13 |
| `muni_notices.json` | Array | **100** | 2026-04-01 08:57:13 |
| `nws_cap.json` | Array | **3** | 2026-04-01 08:57:13 |
| `public_notices_state.json` | Array | **1** | 2026-04-01 08:57:13 |
| `stolen_vehicles.json` | Array | **3,084** | 2026-04-01 08:57:13 |
| `stolen_vehicles_toc.json` | Object | **309** | 2026-04-01 08:57:13 |
| `ua_news.json` | Array | **9** | 2026-04-01 08:57:13 |
| `venues.json` | Object | **1** | 2026-04-01 08:57:13 |
| **STATEWIDE TOTAL** | | **5,420** | |

---

## 📂 Repository Structure

The architecture is strictly separated to ensure bots, developers, and GitHub Actions never trip over each other.

### `/.github/workflows/`
Contains the YAML definitions for our automated CI/CD pipelines and CRON scrapers. Every new data source requires its own isolated workflow file to ensure failures do not cascade.

### `/pipelines/`
Contains the source code for the actual scrapers and data processors. 
- *Example:* `/pipelines/missing-persons-extractor/` (PDF text extraction using `pdfplumber` and Regex).
- *Example:* `/pipelines/adfg-sport-dataset/` (API wrapper and formatter).

### `/schemas/`
Contains standard JSON Schemas or Zod definition files. All pipelines must generate data that strictly matches these schemas before committing, preventing malformed data from crashing client frontend apps.

### `/data/`
The actual JSON payload directory. This is where the GitHub Actions drop their minified output files. **Humans do not manually edit these files.**
- *Active Feeds:* `/data/latest/`
- *Historical Dumps:* `/data/archives/YYYY/` (This allows us to leverage unlimited storage for massive historical datasets).

### `/docs/`
Internal documentation detailing the exact structure of incoming data sources and data dictionaries.

---

## ⚙️ How to Add a New Pipeline

Adding a new automated data feed requires 5 distinct steps:

1. **Write the Pipeline Code:** Create your execution script in `/pipelines/[feed-name]/`. The script must fetch data, process it, and output a strict `.json` artifact.
2. **Define the Schema:** Create a schema definition in `/schemas/[feed-name]-schema.json`.
3. **Draft the Workflow:** Create `.github/workflows/[feed-name]-sync.yml` to set the cron schedule, define the runtime environment, run the pipeline, and commit the diffs back to the repository.
4. **Test Locally:** Run the pipeline locally to ensure it outputs correctly. **NEVER USE REAL API KEYS IN THIS REPO FOR TESTING. USE ENVIRONMENT VARIABLES ONLY.**
5. **Deploy & Monitor:** Push to `main`. Manually trigger the action via the GitHub UI to establish the first baseline data drop.

---

## ⚡ Frontend Consumption Best Practices

When consuming from this API in our visual applications, you must respect the static nature of the CDN cache:

```javascript
// Example: Fetching the Latest Missing Persons Roster with a cache buster parameter to ignore local CDN cache if needed
const CACHE_BUSTER = new Date().getTime();
const API_URL = `https://raw.githubusercontent.com/alaskaintel/intel-json/main/data/latest/missing-persons-roster.json?v=${CACHE_BUSTER}`;

async function fetchLatestIntel() {
  try {
    const response = await fetch(API_URL);
    if (!response.ok) throw new Error('Network response failed');
    return await response.json();
  } catch (error) {
    console.error("Failed to load generic static intel:", error);
  }
}
```

## 📜 Standard Operating Procedures (SOP)

- **Do Not Bloat Data:** Pipelines should output `.json` files that are tightly minified to reduce network payload size for the end user.
- **Fail Gracefully:** If an external state website goes down or changes its DOM, the Action should fail and trigger an email alert—it must **never** commit a blank or malformed `.json` file that overwrites good data.
- **Version Control:** Massive structural changes to a dataset must output to a new file (e.g. `v2-dataset.json`) to keep legacy frontends from crashing during transitions.

> [!IMPORTANT]
> **A Final Warning:** Maintain a zero-trust policy. Because this repository powers our public UI arrays and map overlays, if malformed data is merged, the maps crash. All PRs touching the pipelines or schemas require thorough manual review.
