"""Data-quality checks. Errors stop the run (nothing is committed); warnings are reported."""
from __future__ import annotations

from . import config


class ValidationError(ValueError):
    pass


def check_brand_rows(rows: list[dict], previous: dict[tuple[str, str], float] | None = None) -> list[str]:
    """Validate one day's API rows. Raises ValidationError on hard failures, returns warnings."""
    warnings: list[str] = []
    if len(rows) < config.MIN_PRICES_EXPECTED:
        raise ValidationError(f"only {len(rows)} prices returned (expected >= {config.MIN_PRICES_EXPECTED})")
    brands = {r["brand_code"] for r in rows}
    if len(brands) < config.MIN_BRANDS_EXPECTED:
        raise ValidationError(f"only {len(brands)} brands returned (expected >= {config.MIN_BRANDS_EXPECTED})")
    bad = [r for r in rows if not (config.PRICE_MIN <= float(r["price"]) <= config.PRICE_MAX)]
    if bad:
        raise ValidationError("price out of range: " + ", ".join(
            f"{r['brand_code']}/{r['product_code']}={r['price']}" for r in bad[:10]))
    seen = set()
    for r in rows:
        k = (r["brand_code"], r["product_code"])
        if k in seen:
            raise ValidationError(f"duplicate price for {k}")
        seen.add(k)
    if previous:
        for r in rows:
            old = previous.get((r["brand_code"], r["product_code"]))
            if old and abs(float(r["price"]) - old) / old > config.DAILY_JUMP_WARN:
                warnings.append(f"big move {r['brand_code']}/{r['product_code']}: {old} -> {r['price']}")
    return warnings


def check_structure_rows(rows: list[dict]) -> list[str]:
    warnings: list[str] = []
    for r in rows:
        v = r.get("retail")
        if r["product_code"] in config.PRODUCTS and v not in ("", None):
            if not (config.PRICE_MIN <= float(v) <= config.PRICE_MAX):
                raise ValidationError(f"structure {r['date']} {r['product_code']} retail={v} out of range")
        # retail should roughly equal (wholesale incl. VAT + marketing margin incl. VAT)
        try:
            recon = float(r["wholesale_incl_vat"]) + float(r["marketing_margin"]) + float(r["vat_marketing_margin"])
            if abs(recon - float(r["retail"])) > 0.05:
                warnings.append(f"structure {r['date']} {r['product_code']}: components {recon:.2f} != retail {r['retail']}")
        except (KeyError, TypeError, ValueError):
            pass
    return warnings
