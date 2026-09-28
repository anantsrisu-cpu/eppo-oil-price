#!/usr/bin/env python3
"""Daily job (run by GitHub Actions at ~10:00 Bangkok time).

  1. GET EPPO oil-price API  -> per-brand retail prices of today (no 'Generate' click needed)
  2. validate, save raw JSON (audit trail), upsert into data/retail_prices_brand.csv
  3. fetch any new daily price-structure Excel files (PTT reference + tax/fund/margin)
  4. rebuild SQLite / pivots / Excel / dashboard JSON / daily report

Safe to run many times per day (idempotent). Exit code != 0 => GitHub marks the run failed
and e-mails the repository owner.

Usage:
  python scripts/fetch_daily.py                 # normal daily run
  python scripts/fetch_daily.py --skip-structure
  python scripts/fetch_daily.py --no-build
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eppo import api, build, config, structure, validate  # noqa: E402
from eppo.http import BlockedError, FetchError  # noqa: E402
from eppo.storage import append_log, read_csv, upsert  # noqa: E402

log = logging.getLogger("fetch_daily")


def previous_prices(before: str) -> dict:
    rows = [r for r in read_csv(config.BRAND_CSV) if r["snapshot_date"] < before]
    if not rows:
        return {}
    last = max(r["snapshot_date"] for r in rows)
    return {(r["brand_code"], r["product_code"]): float(r["price"]) for r in rows if r["snapshot_date"] == last}


def fetch_brand_prices(snapshot_date: str, warnings: list[str]) -> int:
    fetched_at = config.now_bkk().isoformat(timespec="seconds")
    raw = api.fetch_raw()
    rows, w = api.parse(raw, snapshot_date, fetched_at)
    warnings += w
    warnings += validate.check_brand_rows(rows, previous_prices(snapshot_date))
    raw_path = api.save_raw(raw, snapshot_date)
    ins, upd = upsert(config.BRAND_CSV, rows, config.BRAND_COLUMNS,
                      key=("snapshot_date", "brand_code", "product_code"))
    log.info("brand prices: %d rows (%d new, %d updated) raw=%s", len(rows), ins, upd, raw_path)
    return ins + upd


def fetch_new_structure(since: str, warnings: list[str], max_pages: int = 1) -> int:
    # seed rows only carry the retail price -> treat them as missing so the full file replaces them
    have = {r["date"] for r in read_csv(config.STRUCTURE_CSV) if not r.get("source_file", "").startswith("seed")}
    files = structure.list_files(since, max_pages=max_pages, per_page=30)
    todo = {d: u for d, u in files.items() if d not in have}
    added = 0
    for d, url in sorted(todo.items()):
        try:
            rows, sha = structure.fetch_and_parse(d, url)
            warnings += validate.check_structure_rows(rows)
            ins, upd = upsert(config.STRUCTURE_CSV, rows, config.STRUCTURE_COLUMNS, key=("date", "product_code"))
            added += ins + upd
            log.info("structure %s: %d rows sha256=%s", d, len(rows), sha[:12])
        except (FetchError, ValueError) as e:
            warnings.append(f"structure file {d} skipped: {e}")
        time.sleep(config.POLITE_DELAY)
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="snapshot date YYYY-MM-DD (default: today Bangkok)")
    ap.add_argument("--skip-structure", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    snapshot_date = a.date or config.today_bkk()
    warnings: list[str] = []
    status, err = "ok", ""
    try:
        changed = fetch_brand_prices(snapshot_date, warnings)
        if not a.skip_structure:
            try:
                # look back 14 days so late / missed files are picked up automatically
                from datetime import date, timedelta
                since = (date.fromisoformat(snapshot_date) - timedelta(days=14)).isoformat()
                changed += fetch_new_structure(max(since, config.HISTORY_START), warnings)
            except FetchError as e:  # structure is secondary - don't fail the whole run
                warnings.append(f"structure listing failed: {e}")
        if not a.no_build:
            build.run(warnings)
        log.info("done - %d changed rows", changed)
    except BlockedError as e:
        status, err = "blocked", str(e)
        log.error("%s", e)
    except (FetchError, validate.ValidationError, ValueError) as e:
        status, err = "error", str(e)
        log.error("%s", e)
    for w in warnings:
        log.warning("%s", w)
    append_log(config.RUN_LOG, {"run_at": config.now_bkk().isoformat(timespec="seconds"),
                                "snapshot_date": snapshot_date, "status": status,
                                "warnings": len(warnings), "error": err[:300]})
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
