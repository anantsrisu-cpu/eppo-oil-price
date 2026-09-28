"""CSV storage helpers. CSV is the source of truth (git-diffable, opens in Excel).

Security: values that start with = + - @ and are *text* get a leading apostrophe when
exported for Excel (see build.py) to prevent CSV/formula injection. Stored CSVs keep raw values.
"""
from __future__ import annotations

import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})
    tmp.replace(path)  # atomic replace -> never leaves a half-written file


def upsert(path: Path, new_rows: list[dict], columns: list[str], key: tuple[str, ...],
           sort_by: tuple[str, ...] | None = None) -> tuple[int, int]:
    """Insert or replace rows by key. Returns (inserted, updated). Idempotent."""
    existing = read_csv(path)
    index = {tuple(str(r.get(k, "")) for k in key): i for i, r in enumerate(existing)}
    inserted = updated = 0
    for r in new_rows:
        r = {c: ("" if r.get(c) is None else str(r.get(c))) for c in columns}
        k = tuple(r[c] for c in key)
        if k in index:
            old = existing[index[k]]
            if any(str(old.get(c, "")) != r[c] for c in columns if c != "fetched_at"):
                existing[index[k]] = r
                updated += 1
        else:
            index[k] = len(existing)
            existing.append(r)
            inserted += 1
    if inserted or updated or not path.exists():
        existing.sort(key=lambda r: tuple(str(r.get(c, "")) for c in (sort_by or key)))
        write_csv(path, existing, columns)
    return inserted, updated


def append_log(path: Path, row: dict) -> None:
    cols = list(row.keys())
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(row)
