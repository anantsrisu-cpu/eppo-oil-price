"""EPPO per-brand retail price archive (หน้า 'ราคาขายปลีกน้ำมัน' -> ปุ่ม Generate / ไอคอนดาวน์โหลด).

EPPO publishes one WordPress post per price change in category 455 ('oil-retail-price-list'),
each with an Excel 97-2003 attachment, e.g.
  https://www.eppo.go.th/wp-content/uploads/2026/04/retail-2018-07-10.xls
Sheet 'ราคาน้ำมันวันนี้': one column per brand (ปตท, บางจาก, เชลล์, เอสโซ่, เชฟรอน, ไออาร์พีซี,
พีทีจี, ซัสโก้, เพียว, ซัสโก้ ดีลเลอร์), one row per product and a row 'มีผลตั้งแต่ (Effective Date)'.
The series runs from Aug 2004 and STOPS on 10 Jul 2018 (checked 28 Sep 2026: 857 posts).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta

from . import config
from .http import get_bytes, get_json
from .structure import _read_grids

log = logging.getLogger(__name__)

# header text (Thai row + English row + 3rd row joined) -> brand code; first match wins
BRAND_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("susco2", re.compile(r"ดีลเลอร์|DEALER", re.I)),
    ("susco1", re.compile(r"ซัสโก้|SUSCO", re.I)),
    ("ptt", re.compile(r"ปตท|\bPTT\b", re.I)),
    ("bcp", re.compile(r"บางจาก|\bBCP\b", re.I)),
    ("shell", re.compile(r"เชลล์|SHELL", re.I)),
    ("esso", re.compile(r"เอสโซ่|ESSO", re.I)),
    ("caltex", re.compile(r"เชฟรอน|CHEVRON|คาลเท็กซ์|CALTEX", re.I)),
    ("irpc", re.compile(r"ไออาร์พีซี|IRPC", re.I)),
    ("pt", re.compile(r"พีทีจี|เอ็นเนอ|\bPTG?\b", re.I)),
    ("pure", re.compile(r"เพียว|PURE", re.I)),
]
# row label -> product code; first match wins (order matters: E85/E20/91 before generic 95)
PRODUCT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("e85", re.compile(r"E85", re.I)),
    ("e20", re.compile(r"E20", re.I)),
    ("gh91", re.compile(r"แก๊สโซฮอล.*91|GASOHOL\s*91", re.I)),
    ("gh95", re.compile(r"95-?E10|แก๊สโซฮอล.*95|GASOHOL\s*95", re.I)),
    ("gl95", re.compile(r"ULG|เบนซิน.*95", re.I)),
    ("dsb20", re.compile(r"B20", re.I)),
    ("dsb10", re.compile(r"B10", re.I)),
    ("pds", re.compile(r"พรีเมี่?ยม|PREMIUM", re.I)),
    ("ds", re.compile(r"HSD|ดีเซล", re.I)),
]
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
_TITLE_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_EFF = re.compile(r"^(\d{1,2})\s*([A-Za-z]{3})[A-Za-z]*\.?\s*(\d{1,2}[:.]\d{2})?")


def _s(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _effective(v, announce: date) -> tuple[str, str]:
    """'10 Jul 05:00' (year implied) or an Excel date number -> ('YYYY-MM-DD', 'HH:MM')."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 30000 < v < 60000:
        dt = datetime(1899, 12, 30) + timedelta(days=float(v))
        return dt.date().isoformat(), dt.strftime("%H:%M")
    if isinstance(v, datetime):
        return v.date().isoformat(), v.strftime("%H:%M")
    m = _EFF.match(_s(v))
    if not m or m[2].upper() not in _MONTHS:
        return "", ""
    month, day = _MONTHS[m[2].upper()], int(m[1])
    year = announce.year - 1 if month > announce.month else announce.year
    try:
        d = date(year, month, day)
    except ValueError:
        return "", ""
    return d.isoformat(), (m[3] or "").replace(".", ":")


def parse_workbook(content: bytes, source_file: str = "") -> list[dict]:
    """One archive .xls -> rows {announce_date, brand_code, product_code, price, effective_*}.
    price '' = the brand did not sell that product on that date (0 in the file)."""
    return parse_grid(_read_grids(content)[0], source_file)


def parse_grid(grid: list[list], source_file: str = "") -> list[dict]:
    m = next((_TITLE_DATE.search(_s(c)) for r in grid[:5] for c in r if _TITLE_DATE.search(_s(c))), None)
    if not m:
        raise ValueError("title 'ราคาน้ำมันวันที่ DD/MM/YYYY' not found")
    announce = date(int(m[3]), int(m[2]), int(m[1]))
    if announce.year > 2400:          # Buddhist-era year, just in case
        announce = announce.replace(year=announce.year - 543)
    hi = next((i for i, r in enumerate(grid) if any("ปตท" in _s(c) or _s(c).upper() == "PTT" for c in r[1:])), None)
    if hi is None:
        raise ValueError("brand header row not found")
    cols: dict[int, str] = {}
    for j in range(1, max(len(r) for r in grid[hi:hi + 3])):
        text = " ".join(_s(grid[hi + k][j]) if j < len(grid[hi + k]) else "" for k in range(3)).strip()
        if not text:
            continue
        code = next((c for c, pat in BRAND_PATTERNS if pat.search(text)), None)
        if code and code not in cols.values():
            cols[j] = code
    if len(cols) < 5:
        raise ValueError(f"only {len(cols)} brand columns recognised")
    eff_i = next((i for i in range(hi + 1, len(grid)) if re.search(r"มีผล|EFFECTIVE", _s(grid[i][0]), re.I)), None)
    if eff_i is None:
        raise ValueError("'มีผลตั้งแต่ (Effective Date)' row not found")
    eff = {j: _effective(grid[eff_i][j] if j < len(grid[eff_i]) else "", announce) for j in cols}

    rows, seen = [], set()
    for i in range(hi + 1, eff_i):
        label = _s(grid[i][0])
        if not label or re.search(r"UNIT|หน่วย", label, re.I):
            continue
        product = next((c for c, pat in PRODUCT_PATTERNS if pat.search(label)), None)
        if product is None:
            log.warning("%s: unknown archive row %r", announce, label)
            continue
        if product in seen:
            continue
        seen.add(product)
        for j, brand in cols.items():
            v = grid[i][j] if j < len(grid[i]) else ""
            price = round(float(v), 2) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else ""
            if price != "" and not (config.PRICE_MIN <= price <= config.PRICE_MAX):
                raise ValueError(f"{announce} {brand}/{product}: price {price} out of range")
            rows.append({"announce_date": announce.isoformat(), "brand_code": brand, "product_code": product,
                         "price": price, "effective_date": eff[j][0] if price != "" else "",
                         "effective_time": eff[j][1] if price != "" else "", "source_file": source_file})
    if not rows:
        raise ValueError("no prices found")
    return rows


def list_files(since: str = "2017-12-01", per_page: int = 100, max_pages: int = 20) -> list[tuple[str, str]]:
    """[(post_date, attachment_url)] for archive posts dated >= since (newest first)."""
    posts: list[dict] = []
    for page in range(1, max_pages + 1):
        items, _ = get_json(config.POSTS_API, {
            "categories": config.ARCHIVE_CATEGORY, "per_page": per_page, "page": page,
            "orderby": "date", "order": "desc", "_fields": "id,date,acf"})
        if not isinstance(items, list) or not items:
            break
        posts += items
        if len(items) < per_page or str(items[-1].get("date", ""))[:10] < since:
            break
        time.sleep(config.POLITE_DELAY)
    out = []
    for p in posts:
        d = str(p.get("date", ""))[:10]
        att = (p.get("acf") or {}).get("attachment_1")
        if d < since or not isinstance(att, int):
            continue
        media, _ = get_json(f"{config.EPPO_BASE}/wp-json/wp/v2/media/{att}", {"_fields": "source_url"})
        url = str((media or {}).get("source_url", ""))
        if url.lower().endswith((".xls", ".xlsx")):
            out.append((d, url))
        time.sleep(config.POLITE_DELAY)
    return out


def fetch_and_parse(url: str) -> list[dict]:
    content, _ = get_bytes(url, accept="application/vnd.ms-excel,*/*")
    return parse_workbook(content, url.rsplit("/", 1)[-1])
