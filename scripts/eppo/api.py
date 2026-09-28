"""Daily per-brand retail prices from the EPPO JSON API.

This is the same data the EPPO page shows in its 'ราคาขายน้ำมัน ณ วันที่ ...' table,
so no need to click 'Generate' in a browser.

Response shape (Sep 2026):
{"status":"success","last_updated":"24 September 2026",
 "data":{"ptt":{"oil_ptt_gh95":"39.94", ..., "oil_ptt_date":"2026-09-24","oil_ptt_time":"05:00"}, ...}}
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from . import config
from .http import get_json

log = logging.getLogger(__name__)
_FIELD = re.compile(r"^oil_(?P<brand>[a-z0-9]+)_(?P<product>[a-z0-9]+)$")


def fetch_raw() -> dict:
    data, _ = get_json(config.OIL_PRICE_API)
    if not isinstance(data, dict):
        raise ValueError("EPPO API returned unexpected JSON type")
    return data


def save_raw(raw: dict, snapshot_date: str) -> str:
    y, m, _ = snapshot_date.split("-")
    folder = config.RAW_API_DIR / y / m
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{snapshot_date}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    return str(path.relative_to(config.ROOT))


def _to_price(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "--", "N/A", "n/a"):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse(raw: dict, snapshot_date: str, fetched_at: str, source: str = "eppo_api") -> tuple[list[dict], list[str]]:
    """Convert raw API JSON to long-format rows. Returns (rows, warnings)."""
    warnings: list[str] = []
    if str(raw.get("status", "")).lower() != "success":
        raise ValueError(f"EPPO API status is not success: {raw.get('status')!r}")
    data = raw.get("data")
    if not isinstance(data, dict) or not data:
        raise ValueError("EPPO API: 'data' missing or empty")

    rows: list[dict] = []
    for brand_code, fields in data.items():
        brand_code = str(brand_code).lower()
        if not isinstance(fields, dict):
            warnings.append(f"brand {brand_code}: unexpected value type")
            continue
        if brand_code not in config.BRANDS:
            warnings.append(f"NEW brand code from EPPO: '{brand_code}' (add it to config.BRANDS)")
        eff_date = str(fields.get(f"oil_{brand_code}_date", "") or "")
        eff_time = str(fields.get(f"oil_{brand_code}_time", "") or "")
        for key, value in fields.items():
            m = _FIELD.match(str(key))
            if not m or m["product"] in ("date", "time"):
                continue
            if m["brand"] != brand_code:
                warnings.append(f"field {key} under brand {brand_code}")
            product = m["product"]
            price = _to_price(value)
            if price is None:
                continue
            if product not in config.PRODUCTS:
                warnings.append(f"NEW product code from EPPO: '{product}' (add it to config.PRODUCTS)")
            rows.append({
                "snapshot_date": snapshot_date,
                "brand_code": brand_code,
                "brand_name_th": config.BRANDS.get(brand_code, {}).get("th", brand_code),
                "product_code": product,
                "product_name_th": config.PRODUCTS.get(product, {}).get("th", product),
                "price": price,
                "effective_date": eff_date,
                "effective_time": eff_time,
                "source": source,
                "fetched_at": fetched_at,
            })

    missing = sorted(set(config.BRANDS) - {r["brand_code"] for r in rows})
    if missing:
        warnings.append("brands with no prices today: " + ", ".join(missing))
    # stale effective dates (e.g. Esso rebranded to Bangchak - EPPO still returns old 2025 prices)
    for b in sorted({r["brand_code"] for r in rows}):
        eff = next((r["effective_date"] for r in rows if r["brand_code"] == b), "")
        try:
            age = (date.fromisoformat(snapshot_date) - date.fromisoformat(eff)).days
            if age > config.STALE_AFTER_DAYS:
                warnings.append(f"brand {b}: effective date {eff} is {age} days old -> marked stale")
        except ValueError:
            warnings.append(f"brand {b}: bad effective date {eff!r}")
    return rows, warnings
