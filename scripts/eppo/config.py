"""Central configuration. If EPPO renames something, this is usually the only file to edit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_API_DIR = DATA_DIR / "raw" / "api"
RAW_STRUCTURE_DIR = DATA_DIR / "raw" / "structure"
REPORTS_DIR = ROOT / "reports"
SITE_SRC = ROOT / "site"          # dashboard source (HTML/CSS/JS, committed)
SITE_OUT = ROOT / "_site"         # built website (NOT committed, deployed to GitHub Pages)
PIVOT_DIR = REPORTS_DIR / "pivots"
DAILY_REPORT_DIR = REPORTS_DIR / "daily"

BRAND_CSV = DATA_DIR / "retail_prices_brand.csv"
STRUCTURE_CSV = DATA_DIR / "price_structure_daily.csv"
SQLITE_DB = SITE_OUT / "downloads" / "oil_prices.sqlite"  # rebuilt every run
RUN_LOG = DATA_DIR / "run_log.csv"

# History starts on 1 Jan 2025 (= 1 ม.ค. 2568)
HISTORY_START = "2025-01-01"

# ---------------------------------------------------------------- time
TZ_BKK = timezone(timedelta(hours=7), name="Asia/Bangkok")  # Thailand has no DST


def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)


def today_bkk() -> str:
    return now_bkk().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- network
# Only these hosts may ever be contacted by the pipeline (defence in depth,
# the GitHub workflow additionally blocks all other egress with harden-runner).
ALLOWED_HOSTS = {"www.eppo.go.th", "eppo.go.th"}

EPPO_BASE = "https://www.eppo.go.th"
OIL_PRICE_API = EPPO_BASE + "/wp-json/oil-api/v1/oil-prices"
MEDIA_API = EPPO_BASE + "/wp-json/wp/v2/media"
STRUCTURE_SEARCH = "pt-price-st"  # daily file name: pt-price-st-YYYY-M-D.xlsx

# Honest, identifiable User-Agent (public data, 1-2 requests/day)
USER_AGENT = "Mozilla/5.0 (compatible; eppo-oil-price-bot/1.0; public data, 1-2 requests per day)"
HTTP_TIMEOUT = 30          # seconds per request
HTTP_RETRIES = 4           # attempts per request
HTTP_BACKOFF = 5           # seconds, doubles each retry
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # refuse anything bigger than 5 MB
POLITE_DELAY = 1.0         # seconds between requests during backfill

# ---------------------------------------------------------------- brands
# colors = validated categorical palette (see site/assets/style.css --b-<code>); 8 hue slots,
# susco2 = neutral gray + dashed line, esso = gray (EPPO data is stale)
# key = brand code used by the EPPO API (data.<code>.oil_<code>_<product>)
BRANDS: dict[str, dict] = {
    "ptt":    {"th": "ปตท.",             "en": "PTT",            "order": 1,  "color": "#2a78d6"},
    "bcp":    {"th": "บางจาก",           "en": "Bangchak",       "order": 2,  "color": "#eb6834"},
    "shell":  {"th": "เชลล์",            "en": "Shell",          "order": 3,  "color": "#1baf7a"},
    "esso":   {"th": "เอสโซ่",           "en": "Esso",           "order": 4,  "color": "#898781"},
    "caltex": {"th": "เชฟรอน (คาลเท็กซ์)", "en": "Chevron/Caltex", "order": 5,  "color": "#eda100"},
    "irpc":   {"th": "ไออาร์พีซี",       "en": "IRPC",           "order": 6,  "color": "#e87ba4"},
    "pt":     {"th": "พีทีจี เอ็นเนอยี (PT)", "en": "PTG Energy (PT)", "order": 7, "color": "#008300"},
    "susco1": {"th": "ซัสโก้",           "en": "Susco",          "order": 8,  "color": "#4a3aa7"},
    "pure":   {"th": "เพียว",            "en": "Pure",           "order": 9,  "color": "#e34948"},
    "susco2": {"th": "ซัสโก้ ดีลเลอร์",   "en": "Susco Dealer (Sinopec/Susco)", "order": 10, "color": "#52514e"},
}

# The price-structure files quote the retail price of the market leader.
# EPPO: "ตัวเลขราคาขายปลีกในโครงสร้างอ้างอิงจากราคาขายปลีกของผู้ประกอบการที่มีส่วนแบ่งการจำหน่ายสูงสุด"
STRUCTURE_REFERENCE_BRAND = "ptt"

# ---------------------------------------------------------------- products
# key = product code used by the EPPO API
PRODUCTS: dict[str, dict] = {
    "gh95":  {"th": "แก๊สโซฮอล์ 95 (E10)",  "en": "Gasohol 95",          "group": "Gasohol",  "order": 1},
    "gh91":  {"th": "แก๊สโซฮอล์ 91",        "en": "Gasohol 91",          "group": "Gasohol",  "order": 2},
    "e20":   {"th": "แก๊สโซฮอล์ E20",       "en": "Gasohol E20",         "group": "Gasohol",  "order": 3},
    "e85":   {"th": "แก๊สโซฮอล์ E85",       "en": "Gasohol E85",         "group": "Gasohol",  "order": 4},
    "gs95p": {"th": "แก๊สโซฮอล์ 95 พรีเมียม", "en": "Gasohol 95 Premium",  "group": "Gasohol",  "order": 5},
    "gs99p": {"th": "แก๊สโซฮอล์ 99 พรีเมียม", "en": "Gasohol 99 Premium",  "group": "Gasohol",  "order": 6},
    "gl95":  {"th": "เบนซิน 95",            "en": "Gasoline 95",         "group": "Gasoline", "order": 7},
    "gl95p": {"th": "เบนซิน 95 พรีเมียม",    "en": "Gasoline 95 Premium", "group": "Gasoline", "order": 8},
    "ds":    {"th": "ดีเซล B7",             "en": "Diesel B7",           "group": "Diesel",   "order": 9},
    "dsb10": {"th": "ดีเซล B10",            "en": "Diesel B10",          "group": "Diesel",   "order": 10},
    "dsb20": {"th": "ดีเซล B20",            "en": "Diesel B20",          "group": "Diesel",   "order": 11},
    "pds":   {"th": "ดีเซลพรีเมียม",         "en": "Premium Diesel",      "group": "Diesel",   "order": 12},
}

# Row labels in the structure Excel -> product code (normalised: upper, single spaces)
STRUCTURE_PRODUCT_MAP: dict[str, str] = {
    "ULG95": "gl95",
    "ULG 95": "gl95",
    "GASOHOL95 E10": "gh95",
    "GASOHOL 95 E10": "gh95",
    "GASOHOL91": "gh91",
    "GASOHOL 91": "gh91",
    "GASOHOL95 E20": "e20",
    "GASOHOL 95 E20": "e20",
    "GASOHOL95 E85": "e85",
    "GASOHOL 95 E85": "e85",
    "H-DIESEL": "ds",
    "H-DIESEL B7": "ds",
    "H-DIESEL B20": "dsb20",
    "H-DIESEL 20": "dsb20",       # label typo seen in EPPO files (Feb 2026)
    "H-DIESEL B10": "dsb10",
    "LPG (BAHT/KILOGRAM)": "lpg",
    "LPG (BAHT/KILOGRAM )": "lpg",
    "FO 600 (1) 2%S": "fo600",
    "FO 1500 (2) 2%S": "fo1500",
}
STRUCTURE_EXTRA_PRODUCTS = {
    "lpg": {"th": "LPG (บาท/กก.)", "en": "LPG (Baht/kg)"},
    "fo600": {"th": "น้ำมันเตา 600", "en": "Fuel oil 600"},
    "fo1500": {"th": "น้ำมันเตา 1500", "en": "Fuel oil 1500"},
}

# Column headers in the structure Excel -> field name
STRUCTURE_COLUMN_MAP: dict[str, str] = {
    "EX-REFIN.": "ex_refinery",
    "EX-REFIN": "ex_refinery",
    "DISCOUNT": "refinery_discount",
    "EXCISE TAX": "excise_tax",
    "M. TAX": "municipal_tax",
    "OIL FUND": "oil_fund",
    "CONSV. FUND": "conservation_fund",
    "WHOLESALE (WS)": "wholesale",
    "VAT (WS)": "vat_wholesale",
    "WS&VAT": "wholesale_incl_vat",
    "WS & VAT": "wholesale_incl_vat",
    "MARKETING MARGIN": "marketing_margin",
    "VAT (MM)": "vat_marketing_margin",
    "RETAIL": "retail",
}
STRUCTURE_FIELDS = [
    "ex_refinery", "refinery_discount", "excise_tax", "municipal_tax", "oil_fund",
    "conservation_fund", "wholesale", "vat_wholesale", "wholesale_incl_vat",
    "marketing_margin", "vat_marketing_margin", "retail",
]

# ---------------------------------------------------------------- validation
PRICE_MIN, PRICE_MAX = 10.0, 100.0      # Baht/litre sanity range
MIN_BRANDS_EXPECTED = 5                 # fail the run if fewer brands come back
MIN_PRICES_EXPECTED = 20                # fail the run if fewer prices come back
STALE_AFTER_DAYS = 60                   # effective date older than this => brand flagged stale
DAILY_JUMP_WARN = 0.15                  # warn if a price moves > 15% day-over-day

# ---------------------------------------------------------------- CSV columns
BRAND_COLUMNS = [
    "snapshot_date", "brand_code", "brand_name_th", "product_code", "product_name_th",
    "price", "effective_date", "effective_time", "source", "fetched_at",
]
STRUCTURE_COLUMNS = ["date", "product_code", "product_label", *STRUCTURE_FIELDS,
                     "fx_thb_usd", "source_file"]
