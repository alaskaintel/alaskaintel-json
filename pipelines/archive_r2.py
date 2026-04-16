#!/usr/bin/env python3
"""
AlaskaIntel R2 Archive Pipeline
================================
Maintains a permanent, compact archive of every article link fingerprint
scraped from Alaska news sources. Stores to Cloudflare R2 (S3-compatible).

Storage is minimal: only metadata (no content bodies) is stored.
  ~500 bytes per article × 500 articles/day = ~90 MB/year

R2 layout:
  alaskaintel-archive/
    links/YYYY/MM/DD.jsonl        ← one file per day, append-on-update
    index/sources/<slug>.jsonl    ← per-source running index
    manifests/latest.json         ← last-30-days summary manifest

Local ledger:
  data/r2_link_archive.jsonl      ← append-only local mirror
  data/r2_seen_hashes.txt         ← dedup: one hash per line
"""

import os
import sys
import json
import re
import hashlib
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOCAL_LEDGER   = Path("data/r2_link_archive.jsonl")
SEEN_HASHES    = Path("data/r2_seen_hashes.txt")
INTEL_FILE     = Path("data/latest_intel.json")
AST_LOG_FILE   = Path("data/ast_logs.json")

# Auto-load .env at module level (works whether called directly or imported)
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

R2_BUCKET      = os.getenv("R2_BUCKET", "srv01-alaskaintel")
R2_ACCOUNT_ID  = os.getenv("R2_ACCOUNT_ID", "")
R2_KEY_ID      = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET      = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT    = os.getenv(
    "R2_ENDPOINT",
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else ""
)

PREFIX = "archive"   # R2 key prefix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Convert source name to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_seen_hashes() -> set:
    if SEEN_HASHES.exists():
        return set(SEEN_HASHES.read_text().splitlines())
    return set()


def save_seen_hashes(hashes: set):
    SEEN_HASHES.write_text("\n".join(sorted(hashes)))


def make_fingerprint(item: Dict) -> Optional[Dict]:
    """Extract compact metadata fingerprint from a signal item."""
    url = item.get("link") or item.get("articleUrl") or item.get("sourceUrl") or ""
    title = item.get("title", "").strip()
    ts = item.get("timestamp", "")
    h = item.get("hash") or hashlib.md5(f"{title}|{url}".encode()).hexdigest()

    if not url.startswith("http") or not title:
        return None

    # Extract tags from dataTag e.g. "[Region: Mat-Su] [Category: Law Enforcement]"
    data_tag = item.get("dataTag", "")
    tags = re.findall(r"\[(?:Region|Category):\s*([^\]]+)\]", data_tag)

    return {
        "hash":             h,
        "url":              url,
        "title":            title,
        "source":           item.get("source", "Unknown"),
        "category":         item.get("category", "Unknown"),
        "topic":            item.get("topic") or item.get("incident_type") or item.get("category", ""),
        "timestamp":        ts,
        "tags":             tags,
        "fingerprinted_at": datetime.now(timezone.utc).isoformat(),
    }


def load_all_items() -> List[Dict]:
    """Load signals from latest_intel.json + ast_logs.json combined."""
    items: list[dict] = []
    for path in [INTEL_FILE, AST_LOG_FILE]:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                items.extend(data)
            except Exception as e:
                print(f"  Warning: could not read {path}: {e}")
    return items


# ---------------------------------------------------------------------------
# Local ledger
# ---------------------------------------------------------------------------

def append_to_ledger(fingerprints: List[Dict]):
    """Append new fingerprints to the local JSONL ledger (one per line)."""
    LOCAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_LEDGER.open("a") as f:
        for fp in fingerprints:
            f.write(json.dumps(fp, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Build per-day and per-source JSONL blobs ready for R2
# ---------------------------------------------------------------------------

def build_upload_payloads(fingerprints: List[Dict]) -> List[Tuple[str, str]]:
    """
    Returns a list of (r2_key, jsonl_content) tuples.
    Groups fingerprints by date (links/YYYY/MM/DD.jsonl)
    and by source (index/sources/<slug>.jsonl).
    """
    by_day: dict[str, list[dict]] = {}
    by_source: dict[str, list[dict]] = {}

    for fp in fingerprints:
        ts = fp.get("timestamp", "")
        date_key = ts[:10] if len(ts) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        year, month, day = date_key[:4], date_key[5:7], date_key[8:10]

        day_key = f"{PREFIX}/links/{year}/{month}/{day}.jsonl"
        by_day.setdefault(day_key, []).append(fp)

        slug = slugify(fp.get("source", "unknown"))
        src_key = f"{PREFIX}/index/sources/{slug}.jsonl"
        by_source.setdefault(src_key, []).append(fp)

    payloads = []
    for key, items in {**by_day, **by_source}.items():
        content = "\n".join(json.dumps(fp, separators=(",", ":")) for fp in items)
        payloads.append((key, content))

    return payloads


def build_manifest(all_seen: set) -> str:
    """Build a latest.json manifest from recent ledger entries."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent: list[dict] = []

    if LOCAL_LEDGER.exists():
        for line in LOCAL_LEDGER.read_text().splitlines():
            try:
                fp = json.loads(line)
                fp_ts = fp.get("fingerprinted_at", "")
                if fp_ts and datetime.fromisoformat(fp_ts.replace("Z", "+00:00")) >= cutoff:
                    recent.append(fp)
            except Exception:
                continue

    # Summarise by source
    by_source: dict[str, int] = {}
    for fp in recent:
        src = fp.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    manifest = {
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "total_archived":   len(all_seen),
        "last_30d_count":   len(recent),
        "sources":          by_source,
    }
    return json.dumps(manifest, indent=2)


# ---------------------------------------------------------------------------
# R2 upload
# ---------------------------------------------------------------------------

def upload_to_r2(payloads: List[Tuple[str, str]], manifest_content: str, dry_run=False):
    """Upload all payloads to Cloudflare R2 (S3-compatible via boto3)."""
    if not R2_KEY_ID or not R2_SECRET or not R2_ENDPOINT:
        print("  ⚠️  R2 credentials not configured — skipping upload")
        print(f"     Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID in .env")
        return

    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        print("  ⚠️  boto3 not installed. Run: pip install boto3")
        return

    if dry_run:
        print(f"  [DRY-RUN] Would upload {len(payloads)+1} objects to R2 bucket: {R2_BUCKET}")
        for key, content in payloads[:5]:
            print(f"    → {key}  ({len(content)} bytes)")
        if len(payloads) > 5:
            print(f"    … and {len(payloads)-5} more")
        print(f"    → {PREFIX}/manifests/latest.json")
        return

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_KEY_ID,
        aws_secret_access_key=R2_SECRET,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    uploaded = 0
    for key, content in payloads:
        try:
            # R2 doesn't support append, so we merge with existing if possible
            existing = ""
            try:
                resp = s3.get_object(Bucket=R2_BUCKET, Key=key)
                existing = resp["Body"].read().decode("utf-8")
            except Exception:
                pass  # object doesn't exist yet, start fresh

            # Merge: existing lines + new lines, dedup by hash
            existing_hashes_local: set[str] = set()
            merged_lines: list[str] = []
            for line in (existing + "\n" + content).splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    h = obj.get("hash", "")
                    if h and h not in existing_hashes_local:
                        existing_hashes_local.add(h)
                        merged_lines.append(line)
                except Exception:
                    merged_lines.append(line)

            final_content = "\n".join(merged_lines)
            s3.put_object(
                Bucket=R2_BUCKET,
                Key=key,
                Body=final_content.encode("utf-8"),
                ContentType="application/x-ndjson",
            )
            uploaded += 1
        except Exception as e:
            print(f"  ✗ Failed to upload {key}: {e}")

    # Upload manifest
    try:
        s3.put_object(
            Bucket=R2_BUCKET,
            Key=f"{PREFIX}/manifests/latest.json",
            Body=manifest_content.encode("utf-8"),
            ContentType="application/json",
        )
        uploaded += 1
    except Exception as e:
        print(f"  ✗ Failed to upload manifest: {e}")

    print(f"  ✓ Uploaded {uploaded} objects to R2 bucket: {R2_BUCKET}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def archive_new_articles(items: Optional[List[Dict]] = None, dry_run=False):
    """
    Main function — call from fetch_intel.py or standalone.
    Fingerprints new articles, appends to local ledger, syncs to R2.
    """
    print("\n" + "=" * 60)
    print("AlaskaIntel R2 Archive Pipeline")
    print("=" * 60)

    seen = load_seen_hashes()
    all_items = items if items is not None else load_all_items()

    new_fps: list[dict] = []
    for item in all_items:
        fp = make_fingerprint(item)
        if not fp:
            continue
        h = fp["hash"]
        if h not in seen:
            new_fps.append(fp)
            seen.add(h)

    print(f"  New articles to archive:  {len(new_fps)}")
    print(f"  Total seen (all-time):    {len(seen)}")

    if not new_fps:
        print("  ✓ Nothing new to archive")
        return

    append_to_ledger(new_fps)
    save_seen_hashes(seen)

    payloads = build_upload_payloads(new_fps)
    manifest = build_manifest(seen)
    upload_to_r2(payloads, manifest, dry_run=dry_run)

    print(f"  ✓ Archived {len(new_fps)} new fingerprints")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlaskaIntel R2 Archive Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded without uploading")
    args = parser.parse_args()

    # Load .env if present
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    archive_new_articles(dry_run=args.dry_run)
