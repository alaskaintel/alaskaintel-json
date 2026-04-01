# 🚨 ALASKAINTEL PUBLIC REPOSITORY RULES 🚨

> [!CAUTION]
> **THIS IS A PUBLIC REPOSITORY.** 
> Every single commit, branch, and file pushed to this repository is visible to the entire world, instantly archived by third-party services, and scraped by automated bots.

Before issuing a Pull Request, running a pipeline, or committing any code, you **MUST** strictly adhere to the following rules. Failure to do so will result in an immediate security breach and widespread data compromise.

---

## 1. Zero-Tolerance for Secrets and Keys

Under absolutely no circumstances may any of the following be pushed to this repository:
- **`.env` files** (Ensure these are strictly mapped in `.gitignore`).
- **Cloudflare R2 Keys / AWS S3 Credentials**
- **GoDaddy SSH or SFTP Credentials**
- **Clerk Authentication Secret Keys**
- **FareHarbor Private API Tokens**
- **Database Connection Strings (e.g., PostgreSQL URIs, MongoDB strings)**
- **WordPress Admin Passwords or App Passwords**

### How to use secrets in GitHub Actions:
If a Python or Node pipeline requires a secret to function (e.g., publishing an alert to a private Slack channel or moving an archive to a private S3 bucket), you must use **GitHub Actions Repository Secrets**.

*Correct Implementation:*
```yaml
env:
  SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

---

## 2. No Personally Identifiable Information (PII)

While AlaskaIntel does aggregate public data, specific pipelines often parse raw documents that contain sensitive PII.

- **You may NOT commit raw, unredacted PDFs** representing domestic violence calls, restricted juvenile encounters, or sealed court documents.
- **You may NOT commit JSON files** that contain social security numbers, unredacted dates of birth (unless legally cleared as public missing persons data), or highly sensitive contact information.
- The pipeline architecture must parse, sanitize, and extract *only* the data deemed strictly public and legally shareable before outputting the final `.json`.

---

## 3. The "Clean Diff" Principle

Because our frontend React/Astro applications consume this data directly from the GitHub CDN (`raw.githubusercontent.com`), we must maintain an absolute guarantee of stability.

1. **Never commit a broken JSON:** A pipeline must validate its output against its schema. If a schema fails, the GitHub Action must fail and halt the commit step. Committing a malformed `[ ]` array or an `undefined` string will literally crash the user-facing map overlays.
2. **Minify Outputs:** To decrease bandwidth usage on frontend applications, configure your JSON serializers to minify outputs (`indent=0`, remove whitespace). 
3. **Atomic Commits:** When a GitHub Action commits scheduled data, it must only include the `.json` modifications. Do not include random pipeline log files, `.pypirc` cache, or temporary `__pycache__` data.

---

## 4. Architectural Separation

To keep this repository pristine and organized:
- **Scraping logic** lives exclusively in `/pipelines/`.
- **Validation** lives exclusively in `/schemas/`.
- **Data output** lives exclusively in `/data/`.

Do not mix Python scripts into the `/data/` folder, and do not place `.json` outputs in the root directory.

---

## 5. Security & PR Protocol

- **Review all diffs carefully:** If you are modifying a pipeline, ensure your `print()` statements do not accidentally output a secret token into the GitHub Actions console log, as those logs are also public.
- **Maintain the `.gitignore`:** The `.gitignore` must be aggressive, blocking `venv`, `node_modules`, `.env`, `.DS_Store`, and `__pycache__`.
- **If a secret is ever pushed:** You must immediately assume it is compromised. You cannot simply "delete the file and push the commit" because git history retains it. The secret must be instantly revoked and rotated on the provider's dashboard.

By committing to this repository, you acknowledge that you are handling public-facing infrastructure. Code responsibly.
