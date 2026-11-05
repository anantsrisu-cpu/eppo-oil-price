#!/usr/bin/env python3
"""News job (run by .github/workflows/news-update.yml every ~20 minutes).

  1. GET Google News RSS searches for Thai retail oil price news (read-only, no key)
  2. keep headlines about retail fuel prices, classify them (price change? up/down? which fuels?)
  3. upsert into data/news/oil_price_news.csv (remembers when each headline was first seen)

The dashboard ("ข่าวแจ้งปรับราคาน้ำมัน") and the "fastest website" ranking are built from that CSV by
scripts/build_outputs.py. Exit code 1 only when every query failed AND nothing new was stored for 24 h.

Usage:
  python scripts/fetch_news.py                       # fetch + save
  python scripts/fetch_news.py --from-file feed.xml  # offline: parse a saved RSS file instead
  python scripts/fetch_news.py --dry-run             # show what would be stored, change nothing
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eppo import config, news  # noqa: E402
from eppo.storage import read_csv  # noqa: E402

log = logging.getLogger("fetch_news")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-file", action="append", help="parse saved RSS file(s) instead of the network")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = config.now_bkk()
    errors: list[str] = []
    if a.from_file:
        items = [it for f in a.from_file for it in news.parse_rss(Path(f).read_bytes())]
    else:
        items, errors = news.fetch_feeds()
    for e in errors:
        log.warning("%s", e)
    existing = read_csv(config.NEWS_CSV)
    if errors and len(errors) == len(config.NEWS_QUERIES):
        # one bad poll is not worth an e-mail (the job runs every ~20 min); fail only when nothing new
        # has been stored for a day, i.e. Google News is really unreachable / blocking GitHub
        last = max((r.get("first_seen_at", "") for r in existing), default="")
        stale = not last or news.parse_iso(last) < now - timedelta(hours=24)
        log.log(logging.ERROR if stale else logging.WARNING,
                "all news queries failed - nothing saved (last new item: %s)", last or "never")
        return 1 if stale else 0
    rows, stats = news.merge(existing, items, now)
    changed = bool(stats.get("new") or stats.get("updated") or stats.get("pruned"))
    log.info("news: %d feed items -> %s (total stored %d)", len(items), stats or "no changes", len(rows))
    if a.dry_run:
        for r in rows[-40:]:
            print(r["pub_at"], r["source_domain"], r["kind"], r["direction"], r["effective_date"], r["title"][:70])
        return 0
    if changed or not config.NEWS_CSV.exists():
        news.save(rows, now)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
