#!/usr/bin/env python3
"""Download EPPO's per-brand retail price archive (the data behind the 'Generate' button /
download icons on the page 'ราคาขายปลีกน้ำมัน') into data/archive_retail_brand.csv.

EPPO stopped this series on 10 Jul 2018, so this only needs to run once (the workflow runs it
in 'backfill' mode). Files already in the CSV are skipped unless --force.

  python scripts/backfill_archive.py                  # 2018 (start = config.HISTORY_START)
  python scripts/backfill_archive.py --since 2004-01-01 --no-build   # whole archive 2004-2018
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eppo import archive, build, config  # noqa: E402
from eppo.http import FetchError  # noqa: E402
from eppo.storage import read_csv, upsert  # noqa: E402

log = logging.getLogger("backfill_archive")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # one extra month so the prices valid on the start date are known
    default_since = (date.fromisoformat(config.HISTORY_START) - timedelta(days=45)).isoformat()
    ap.add_argument("--since", default=default_since)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    have = {r["source_file"] for r in read_csv(config.ARCHIVE_CSV)}
    warnings: list[str] = []
    try:
        files = archive.list_files(a.since)
    except FetchError as e:
        log.error("cannot list archive: %s", e)
        if not a.no_build:
            build.run([f"archive: ดึงรายการคลังราคารายแบรนด์ไม่ได้ ({e})"])
        return 1
    todo = [(d, u) for d, u in files if a.force or u.rsplit("/", 1)[-1] not in have]
    log.info("archive: %d files since %s, %d to download", len(files), a.since, len(todo))
    failed = 0
    for i, (d, url) in enumerate(todo, 1):
        try:
            rows = archive.fetch_and_parse(url)
            upsert(config.ARCHIVE_CSV, rows, config.ARCHIVE_COLUMNS,
                   key=("announce_date", "brand_code", "product_code"))
            log.info("[%d/%d] %s ok (%d prices)", i, len(todo), url.rsplit("/", 1)[-1], len(rows))
        except (FetchError, ValueError) as e:
            failed += 1
            warnings.append(f"archive {d} skipped: {e}")
            log.warning("[%d/%d] %s FAILED: %s", i, len(todo), url, e)
        time.sleep(config.POLITE_DELAY)
    if not a.no_build:
        build.run(warnings)
    return 1 if failed and failed == len(todo) else 0


if __name__ == "__main__":
    sys.exit(main())
