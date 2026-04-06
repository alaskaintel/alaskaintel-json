#!/usr/bin/env python3
"""
compile_month_archives.py
─────────────────────────
Recompiles public/archive/YYYY/MM.json files from the raw daily archive files
in archive/YYYY/MM/*.json.

Usage:
    python3 pipelines/compile_month_archives.py           # all years
    python3 pipelines/compile_month_archives.py --year 2025
    python3 pipelines/compile_month_archives.py --year 2025 --month 01

Run from the alaskaintel-json/ directory.
"""

import json
import os
import glob
import argparse
from datetime import datetime, timezone

ARCHIVE_DIR = "archive"
PUBLIC_DIR = "public/archive"


def compile_month(year: str, month: str) -> int:
    """Read all daily JSON files for a YYYY/MM, merge, dedup, write public aggregate."""
    daily_pattern = os.path.join(ARCHIVE_DIR, year, month, "*.json")
    daily_files = sorted(glob.glob(daily_pattern))

    if not daily_files:
        print(f"  [{year}/{month}] No daily files found — skipping.")
        return 0

    # Load existing public aggregate (preserve any enriched data)
    public_path = os.path.join(PUBLIC_DIR, year, f"{month}.json")
    merged: dict[str, dict] = {}

    if os.path.exists(public_path):
        try:
            with open(public_path, "r") as f:
                existing = json.load(f)
            for item in existing:
                key = item.get("hash") or item.get("id")
                if key:
                    merged[key] = item
        except Exception as e:
            print(f"  [{year}/{month}] Warning: could not load existing public file: {e}")

    # Load and merge all daily files
    raw_total = 0
    for filepath in daily_files:
        try:
            with open(filepath, "r") as f:
                daily = json.load(f)
            if not isinstance(daily, list):
                continue
            for item in daily:
                key = item.get("hash") or item.get("id")
                if not key:
                    continue
                # Prefer existing enriched record, but surface new ones
                if key not in merged:
                    merged[key] = item
                raw_total += 1
        except Exception as e:
            print(f"  [{year}/{month}] Warning: could not load {filepath}: {e}")

    if not merged:
        print(f"  [{year}/{month}] No valid signals found — skipping.")
        return 0

    # Sort by timestamp descending
    def ts_key(item):
        ts = item.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    sorted_items = sorted(merged.values(), key=ts_key, reverse=True)

    # Write output
    os.makedirs(os.path.join(PUBLIC_DIR, year), exist_ok=True)
    with open(public_path, "w") as f:
        json.dump(sorted_items, f, indent=2)

    net_gain = len(sorted_items) - (len(merged) - len(sorted_items) + len(sorted_items))
    print(f"  [{year}/{month}] ✓  {len(daily_files)} daily files → {len(sorted_items)} signals  (path: {public_path})")
    return len(sorted_items)


def rebuild_manifest():
    """Regenerate public/archive/manifest.json from what's on disk."""
    pattern = os.path.join(PUBLIC_DIR, "*", "*.json")
    files = glob.glob(pattern)
    keys = []
    for f in files:
        parts = f.replace("\\", "/").split("/")
        # expecting .../public/archive/YYYY/MM.json
        if len(parts) >= 2:
            year = parts[-2]
            month = parts[-1].replace(".json", "")
            if year.isdigit() and month.isdigit() and "manifest" not in f and "pulse" not in f:
                keys.append(f"{year}/{month}")
    keys = sorted(set(keys), reverse=True)
    manifest_path = os.path.join(PUBLIC_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(keys, f, indent=2)
    print(f"\n📋 Manifest rebuilt: {len(keys)} months indexed → {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description="Recompile monthly public archive files.")
    parser.add_argument("--year", type=str, default=None, help="4-digit year (default: all)")
    parser.add_argument("--month", type=str, default=None, help="2-digit month (default: all)")
    args = parser.parse_args()

    # Discover which years/months to process
    if args.year:
        years = [args.year]
    else:
        years = sorted([
            d for d in os.listdir(ARCHIVE_DIR)
            if os.path.isdir(os.path.join(ARCHIVE_DIR, d)) and d.isdigit()
        ])

    months = (
        [args.month]
        if args.month
        else [f"{m:02d}" for m in range(1, 13)]
    )

    print(f"🗂  Compiling archives for years={years}, months={months}\n")

    total_signals = 0
    for year in years:
        for month in months:
            total_signals += compile_month(year, month)

    rebuild_manifest()

    print(f"\n✅ Done. Total signals compiled across all months: {total_signals:,}")


if __name__ == "__main__":
    main()
