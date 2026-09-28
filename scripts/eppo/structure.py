"""Daily oil price-structure Excel files (โครงสร้างราคาขายปลีกน้ำมัน).

EPPO publishes one file per business day, e.g.
  https://www.eppo.go.th/wp-content/uploads/2026/09/pt-price-st-2026-9-25.xlsx
Sheet 'Oil Price Structure' has a header row (EX-REFIN. ... RETAIL) and one row per product.
The RETAIL column = retail price of the market leader (PTT) in Bangkok.
We use these files to build history from 2025-01-01, because EPPO's per-brand
archive ('Generate' / download icons) only goes up to July 2018.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import time
from datetime import date, datetime, timedelta

from . import config
from .http import get_bytes, get_json

log = logging.getLogger(__name__)
_NAME = re.compile(r"pt-price-st-?(\d{4})[-_](\d{1,2})[-_](\d{1,2})\.xlsx?$", re.I)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().upper()


def date_from_url(url: str) -> str | None:
    m = _NAME.search(url)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def list_files(since: str, max_pages: int = 80, per_page: int = 100) -> dict[str, str]:
    """Return {YYYY-MM-DD: url} for structure files dated >= since (newest first paging)."""
    found: dict[str, str] = {}
    for page in range(1, max_pages + 1):
        items, _ = get_json(config.MEDIA_API, {
            "search": config.STRUCTURE_SEARCH, "per_page": per_page, "page": page,
            "orderby": "date", "order": "desc", "_fields": "source_url,date",
        })
        if not isinstance(items, list) or not items:
            break
        for it in items:
            url = str(it.get("source_url", ""))
            d = date_from_url(url)
            if d and d >= since and url.lower().endswith((".xlsx", ".xls")):
                # keep the first (= most recently uploaded) file for each date
                found.setdefault(d, url)
        # NOTE: media is ordered by *upload* date, and EPPO bulk-uploaded old years in 2026,
        # so we cannot stop early on old file dates - we scan up to max_pages.
        if len(items) < per_page:
            break
        time.sleep(config.POLITE_DELAY)
    return dict(sorted(found.items()))


def parse_workbook(content: bytes, file_date: str, source_url: str = "") -> list[dict]:
    """Parse one structure workbook into rows (header-driven, tolerant to column moves)."""
    from openpyxl import load_workbook  # imported lazily so the API job works without it

    if content[:2] != b"PK":
        raise ValueError("not an .xlsx file (old .xls files are not supported)")
    wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    ws.reset_dimensions()  # some Excel files declare a wrong used-range
    grid = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()

    header_idx = next((i for i, r in enumerate(grid) if any(_norm(c) == "RETAIL" for c in r)), None)
    if header_idx is None:
        raise ValueError("header row with 'RETAIL' not found")
    colmap = {}
    label_col = None
    for j, c in enumerate(grid[header_idx]):
        key = config.STRUCTURE_COLUMN_MAP.get(_norm(c))
        if key:
            colmap[j] = key
        elif "UNIT" in _norm(c) and label_col is None:
            label_col = j
    if "retail" not in colmap.values():
        raise ValueError("RETAIL column missing")
    label_col = label_col if label_col is not None else 1

    # sheet date (Excel serial or datetime above the header) - used as a cross-check only
    sheet_date = None
    for r in grid[:header_idx]:
        for c in r:
            if isinstance(c, datetime):
                sheet_date = c.date().isoformat()
            elif isinstance(c, (int, float)) and 40000 < c < 60000:
                sheet_date = (date(1899, 12, 30) + timedelta(days=int(c))).isoformat()
    if sheet_date and sheet_date != file_date:
        log.warning("%s: sheet date %s differs from file name date", file_date, sheet_date)

    rows, fx = [], None
    for r in grid[header_idx + 1:]:
        label = _norm(r[label_col] if label_col < len(r) else "")
        if not label:
            continue
        if label.startswith("EXCHANGE"):
            fx = next((c for c in r if isinstance(c, (int, float))), None)
            break
        code = config.STRUCTURE_PRODUCT_MAP.get(label)
        if code is None:
            log.warning("%s: unknown structure row %r (add to STRUCTURE_PRODUCT_MAP)", file_date, label)
            code = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        rec = {"date": file_date, "product_code": code, "product_label": label}
        for j, key in colmap.items():
            v = r[j] if j < len(r) else None
            rec[key] = round(float(v), 4) if isinstance(v, (int, float)) else ""
        rows.append(rec)
    for rec in rows:
        rec["fx_thb_usd"] = round(float(fx), 4) if isinstance(fx, (int, float)) else ""
        rec["source_file"] = source_url.rsplit("/", 1)[-1]
    if not rows:
        raise ValueError("no product rows found")
    return rows


def fetch_and_parse(file_date: str, url: str) -> tuple[list[dict], str]:
    content, _ = get_bytes(url, accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*")
    return parse_workbook(content, file_date, url), hashlib.sha256(content).hexdigest()
