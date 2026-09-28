#!/usr/bin/env python3
"""Import the bundled seed data (collected on 25 Sep 2026) so the dashboard has history
on day one, even before the first GitHub Actions backfill runs.

  data/seed/structure_retail_compact.json -> PTT retail per product, 2025-01-02 .. 2026-09-25
      (retail column of EPPO daily structure files; 443 business days)
  data/raw/api/2026/09/2026-09-25.json    -> per-brand snapshot of 25 Sep 2026

Seed rows are tagged source_file='seed:...' and are replaced automatically by the full
backfill (scripts/backfill_structure.py), which also adds taxes / funds / marketing margin.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eppo import api, build, config  # noqa: E402
from eppo.storage import upsert  # noqa: E402


def expand_compact(obj: dict) -> list[dict]:
    d0 = date.fromisoformat(obj["d0"])
    dates = [(d0 + timedelta(days=int(x))).isoformat() for x in obj["dates"]]
    presence = obj.get("presence", {})
    rows = []
    for label, changes in obj["retail"].items():
        code = config.STRUCTURE_PRODUCT_MAP.get(label.upper(), label.lower())
        first_i, last_i = presence.get(label, [0, len(dates) - 1])
        ci, val = 0, None
        for i, d in enumerate(dates):
            while ci < len(changes) and changes[ci][0] <= i:
                val = changes[ci][1]
                ci += 1
            if val is None or not (first_i <= i <= last_i):
                continue
            rows.append({"date": d, "product_code": code, "product_label": label, "retail": val,
                         "source_file": "seed:structure_retail_compact.json"})
    return rows


def main() -> int:
    seed = json.loads((config.DATA_DIR / "seed" / "structure_retail_compact.json").read_text(encoding="utf-8"))
    checksum = sum((i + 1) * round(v * 100) for p in seed["retail"].values() for i, v in p)
    if checksum != seed["checksum"]:
        raise SystemExit(f"seed checksum mismatch {checksum} != {seed['checksum']}")
    rows = expand_compact(seed)
    ins, upd = upsert(config.STRUCTURE_CSV, rows, config.STRUCTURE_COLUMNS, key=("date", "product_code"))
    print(f"structure seed: {len(rows)} rows ({ins} new, {upd} updated)")

    for f in sorted(config.RAW_API_DIR.rglob("*.json")):
        snap = f.stem
        brows, warns = api.parse(json.loads(f.read_text(encoding="utf-8")), snap,
                                 f"{snap}T10:00:00+07:00", source="eppo_api")
        ins, upd = upsert(config.BRAND_CSV, brows, config.BRAND_COLUMNS,
                          key=("snapshot_date", "brand_code", "product_code"))
        print(f"api snapshot {snap}: {len(brows)} rows ({ins} new) warnings={len(warns)}")
    build.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
