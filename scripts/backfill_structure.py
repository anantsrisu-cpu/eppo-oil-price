#!/usr/bin/env python3
"""One-time (or occasional) history backfill from EPPO daily price-structure files.

Downloads every 'pt-price-st-YYYY-M-D.xlsx' dated >= --start (default 2025-01-01),
parses tax / fund / marketing margin / retail per product and upserts into
data/price_structure_daily.csv. Skips dates already present unless --force.

  python scripts/backfill_structure.py                    # 2025-01-01 -> today
  python scripts/backfill_structure.py --start 2025-06-01 --end 2025-06-30 --force

Polite: 1 request per second, ~450 files for 2025-2026 => about 10 minutes.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eppo import build, config, structure, validate  # noqa: E402
from eppo.http import FetchError  # noqa: E402
from eppo.storage import read_csv, upsert  # noqa: E402

log = logging.getLogger("backfill")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=config.HISTORY_START)
    ap.add_argument("--end", default=None)
    ap.add_argument("--force", action="store_true", help="re-download dates that already exist")
    ap.add_argument("--max-pages", type=int, default=80)
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    have = {r["date"] for r in read_csv(config.STRUCTURE_CSV)
            if not r.get("source_file", "").startswith("seed")}
    try:
        files = structure.list_files(a.start, max_pages=a.max_pages)
    except FetchError as e:   # EPPO unreachable: keep the seed data and still build the dashboard
        log.error("cannot list structure files: %s", e)
        if not a.no_build:
            build.run([f"backfill: ดึงรายชื่อไฟล์โครงสร้างราคาไม่ได้ ({e})"])
        return 1
    if a.end:
        files = {d: u for d, u in files.items() if d <= a.end}
    todo = {d: u for d, u in files.items() if a.force or d not in have}
    log.info("found %d files since %s, %d to download", len(files), a.start, len(todo))

    warnings, failed = [], []
    for i, (d, url) in enumerate(sorted(todo.items()), 1):
        try:
            rows, _ = structure.fetch_and_parse(d, url)
            warnings += validate.check_structure_rows(rows)
            upsert(config.STRUCTURE_CSV, rows, config.STRUCTURE_COLUMNS, key=("date", "product_code"))
            log.info("[%d/%d] %s ok (%d rows)", i, len(todo), d, len(rows))
        except (FetchError, ValueError) as e:
            failed.append((d, str(e)))
            log.warning("[%d/%d] %s FAILED: %s", i, len(todo), d, e)
        time.sleep(config.POLITE_DELAY)

    for d, e in failed:
        warnings.append(f"structure {d} not available: {e}")
    if not a.no_build:
        build.run(warnings)
    log.info("backfill finished: %d ok, %d failed", len(todo) - len(failed), len(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
