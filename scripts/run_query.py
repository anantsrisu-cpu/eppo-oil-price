#!/usr/bin/env python3
"""Run SQL against the built SQLite database (read-only).

  python scripts/run_query.py "SELECT * FROM v_latest WHERE product_code='gh95'"
  python scripts/run_query.py -f sql/queries.sql -n 3        # run query #3 from the file
  python scripts/run_query.py -f sql/queries.sql --list      # list queries in the file
  python scripts/run_query.py "SELECT * FROM v_monthly" --csv out.csv

Database: _site/downloads/oil_prices.sqlite (created by build_outputs.py / fetch_daily.py)
You can also open it with DB Browser for SQLite, DBeaver, Excel (ODBC) or Power BI.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eppo import config  # noqa: E402


def split_queries(text: str) -> list[tuple[str, str]]:
    """Queries in the file are separated by lines like: -- [3] title"""
    parts = re.split(r"^--\s*\[(\d+)\]\s*(.*)$", text, flags=re.M)
    out = []
    for i in range(1, len(parts), 3):
        out.append((f"[{parts[i]}] {parts[i + 1].strip()}", parts[i + 2].strip().rstrip(";")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sql", nargs="?")
    ap.add_argument("-f", "--file")
    ap.add_argument("-n", "--number", type=int)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--csv")
    ap.add_argument("--db", default=str(config.SQLITE_DB))
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()

    if a.file:
        qs = split_queries(Path(a.file).read_text(encoding="utf-8"))
        if a.list or a.number is None:
            for t, _ in qs:
                print(t)
            return 0
        title, sql = next(q for q in qs if q[0].startswith(f"[{a.number}]"))
        print("--", title)
    else:
        sql = a.sql
    if not sql:
        ap.error("give SQL text or -f FILE -n N")
    if not Path(a.db).exists():
        sys.exit(f"{a.db} not found - run: python scripts/build_outputs.py")

    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)   # read-only connection
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if a.csv:
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"saved {len(rows)} rows -> {a.csv}")
        return 0
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows[:a.limit])) if rows else len(str(c))
              for i, c in enumerate(cols)]
    print(" | ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows[:a.limit]:
        print(" | ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    if len(rows) > a.limit:
        print(f"... {len(rows) - a.limit} more rows (use --limit or --csv)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
