"""Online news that announces retail oil price changes -> which website reports first.

Source: Google News RSS search (one read-only feed that covers every Thai news site; each item has
the publisher's name + site and its publication time). See config.NEWS_* for queries / site lists.

Pipeline
--------
1. ``fetch_feeds``   GET a few Google News RSS searches (via the hardened http client)
2. ``parse_rss``     XML -> items (DTD/entities refused, text cleaned, https links only)
3. ``classify``      Thai headline rules -> kind (adjust = announces a price change, daily = price list),
                     direction (up/down/freeze), fuels, amounts (Baht/litre), effective date, template flag
4. ``merge``         upsert into data/news/oil_price_news.csv, remembering when *we* first saw each
                     item and when its headline first announced a change
5. ``build_events``  group "adjust" news by effective date, rank sites by the time they reported
6. ``ranking``       per site: how often it was first / in the top 3, median minutes behind the first

Timing rule (honest "who was first")
------------------------------------
* Normal articles: the publisher's own publication time (RSS pubDate).
* "Template" articles (daily "ราคาน้ำมันพรุ่งนี้ / วันนี้" pages that are created early and edited later):
  their pubDate can be hours before the announcement, so we use the time our poller first saw the
  price-change headline (an upper bound, shown as "ไม่เกิน HH:MM") unless we saw it within
  NEWS_TEMPLATE_TRUST_MIN minutes of publication. Template items found on the very first run cannot
  be timed and are left out of the ranking.
* Google keeps exact times only ~3 days (older items read 07:00:00 GMT) -> such times are date-only and
  are never used for ranking.
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from statistics import median

from . import config
from .http import FetchError, get_bytes
from .storage import read_csv, write_csv

log = logging.getLogger(__name__)
BKK = config.TZ_BKK

# ------------------------------------------------------------------ text helpers
_TAG = re.compile(r"<[^>]+>")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏ -‮﻿]")


def clean_text(s: str | None) -> str:
    s = html.unescape(html.unescape(s or ""))
    s = _CTRL.sub("", _TAG.sub(" ", s))
    return re.sub(r"\s+", " ", s).strip()[: config.NEWS_MAX_TITLE]


def site_domain(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url or "")
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    host = p.hostname.lower()
    return host[4:] if host.startswith("www.") else host


def safe_link(url: str) -> str:
    """Only plain https links leave this module (they end up as <a href> in the dashboard)."""
    url = (url or "").strip()
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or not p.hostname or any(c in url for c in "\"'<> \n\r\t"):
        return ""
    return url


def source_name(domain: str, fallback: str) -> str:
    return config.NEWS_SOURCE_NAMES.get(domain) or fallback or domain


def is_excluded(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in config.NEWS_EXCLUDE_DOMAINS)


def iso(dt: datetime | None) -> str:
    return dt.astimezone(BKK).isoformat(timespec="minutes") if dt else ""


def parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


# ------------------------------------------------------------------ 1/2. feed
def parse_rss(body: bytes) -> list[dict]:
    """RSS 2.0 (Google News) -> list of items. Refuses DTDs/entities (XXE, 'billion laughs')."""
    low = body[:200000].lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise ValueError("RSS with DTD/entities refused")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise ValueError(f"not valid RSS/XML: {e}") from e
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        src_name = clean_text(src.text if src is not None else "")
        src_url = (src.get("url") if src is not None else "") or ""
        title = clean_text(it.findtext("title"))
        for suffix in {" - " + src_name, " - " + site_domain(src_url)}:   # Google appends " - <source>"
            if suffix.strip(" -") and title.endswith(suffix):
                title = title[: -len(suffix)].rstrip()
        link = safe_link(it.findtext("link") or "")
        guid = clean_text(it.findtext("guid")) or link
        pub_raw = (it.findtext("pubDate") or "").strip()
        try:
            pub = parsedate_to_datetime(pub_raw)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, IndexError):
            pub = None
        domain = site_domain(src_url)
        if not (title and link and guid and pub and domain):
            continue
        utc = pub.astimezone(timezone.utc)
        out.append({
            "guid": guid[:200], "title": title, "link": link, "source_domain": domain,
            "source_name": source_name(domain, src_name), "pub": pub,
            # Google shows only the date (07:00:00 GMT) for items older than ~3 days
            "pub_precise": not (utc.hour == 7 and utc.minute == 0 and utc.second == 0),
        })
    return out


def feed_url(query: str) -> str:
    return config.NEWS_RSS + "?" + urllib.parse.urlencode({"q": query, **config.NEWS_RSS_PARAMS})


def fetch_feeds(queries: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Fetch all queries. Returns (items de-duplicated by guid, error messages)."""
    items: dict[str, dict] = {}
    errors = []
    for i, q in enumerate(queries or config.NEWS_QUERIES):
        if i:
            time.sleep(config.POLITE_DELAY)
        try:
            body, _ = get_bytes(feed_url(q), accept="application/rss+xml, application/xml;q=0.9, */*;q=0.5",
                                retries=2)
            got = parse_rss(body)
            log.info("news query %r: %d items", q, len(got))
            for it in got:
                items.setdefault(it["guid"], it)
        except (FetchError, ValueError) as e:
            errors.append(f"news query {q!r} failed: {e}")
    return list(items.values()), errors


# ------------------------------------------------------------------ 3. headline rules (Thai)
_FIX = [(re.compile(r"ขี้น"), "ขึ้น"), (re.compile(r"ลง(ทุน|พื้นที่|นาม|ทะเบียน|มติ|ตัว)"), r"_\1"),
        (re.compile(r"ขึ้น(ไหม|มั้ย|หรือ)"), r"_\1"), (re.compile(r"(ลด|ลง)(ไหม|มั้ย|หรือ)"), r"_\2")]
# always off-topic: protests / demands / forecasts / analysis / other prices
EXCLUDE_RE = re.compile(
    r"ม็อบ|ชุมนุม|เรียกร้อง|ประท้วง|จี้|ขู่|ข้อเสนอ|ฝ่ายค้าน|คาดการณ์|ลุ้น|เตรียม(ปรับ|ขึ้น|ลด)|จ่อ(ปรับ|ขึ้น|ลด|บีบ)|"
    r"เล็ง|ชำแหละ|วิเคราะห์|ไร่ละ|ค่าโดยสาร|ค่าขนส่ง|ค่าครองชีพ|เงินเฟ้อ|ทองคำ|ทองปิด|ดาวโจนส์", re.I)
# world-market words: off-topic UNLESS the headline also names a local retail announcement
MARKET_RE = re.compile(r"น้ำมัน(ดิบ|โลก)|ตลาดโลก|WTI|เบรนท์|เบรนต์|หุ้น(?!ธุรกิจ)|ดอลลาร์|เหรียญ|\$|ต้นทุน|หน้าโรงกลั่น", re.I)
LOCAL_RE = re.compile(r"กบน|ปตท|บางจาก|\bOR\b|BCP|PTG|ปั๊ม|มีผล|ขายปลีก|สตางค์|สต\.|ส\.ต", re.I)
CHANGE_RE = re.compile(
    r"ปรับ\s*(ขึ้น|ลด|ลง|เพิ่ม)|(ขึ้น|ลด|หั่น|ตรึง|ขยับ)\s*ราคา|ราคา\S{0,25}?(ขึ้น|ลง|ลด)|น้ำมัน\S{0,10}?(ขึ้น|ลง|ลด|พุ่ง)|"
    r"(ขึ้น|ลด|ลง)\s*(อีก\s*)?(ดีเซล|เบนซิน|แก๊สโซฮอล|โซฮอล|E\s?\d{2}|B\s?\d{1,2}|LPG|NGV|กลุ่ม)|"
    r"(ขึ้น|ลด|ลง)\s*(อีก\s*)?[\d.,]+\s*(สต|ส\.ต|บาท|บ\.)|ราคาคงเดิม|คงราคา", re.I)
EVIDENCE_RE = re.compile(r"มีผล|พรุ่งนี้|ประกาศ|มติ|เคาะ|ด่วน|แจ้ง|เริ่ม\s*\d|ตั้งแต่|ลิตรละ|/ลิตร|ต่อลิตร")
DAILY_RE = re.compile(r"ราคาน้ำมัน\s*(วัน)?(นี้|พรุ่งนี้)|ราคาน้ำมัน(วัน)?\s*\d|ราคาน้ำมันประจำวัน|ราคาน้ำมันล่าสุด|"
                      r"อัปเดต\s*ราคาน้ำมัน|เช็ก\s*!?\s*ราคาน้ำมัน|ส่องราคา\s*น้ำมัน")
TEMPLATE_RE = re.compile(r"^.{0,20}?(ราคาน้ำมัน\s*(วัน)?(นี้|พรุ่งนี้)|ราคาน้ำมัน(วัน)?\s*\d|ราคาน้ำมันประจำวัน|"
                         r"ราคาน้ำมันล่าสุด|เช็ก\s*!?\s*ราคาน้ำมัน)")
UP_RE = re.compile(r"ขึ้น|เพิ่ม|พุ่ง|ขยับ")
DOWN_RE = re.compile(r"ลด|ลง|หั่น|ดิ่ง|ร่วง")
FREEZE_RE = re.compile(r"ตรึง|คงเดิม|คงราคา")

# fuel tags: specific patterns first (their text is removed before the generic ones run)
FUELS = [
    ("ดีเซล B20", r"(ดีเซล\s*)?(B\s?20|บี\s?20)"),
    ("ดีเซลพรีเมียม", r"(ซูเปอร์\s*พาวเวอร์|ไฮ\s*พรีเมียม|พรีเมียม|V-?POWER)\s*ดีเซล|ดีเซล\s*พรีเมียม"),
    ("ดีเซล", r"ดีเซล|B\s?7\b|บี\s?7"),
    ("แก๊สโซฮอล์ E20", r"(แก๊สโซฮอล์?\s*)?(E\s?20|อี\s?20)"),
    ("แก๊สโซฮอล์ E85", r"(แก๊สโซฮอล์?\s*)?(E\s?85|อี\s?85)"),
    ("แก๊สโซฮอล์ 95", r"(แก๊ส)?โซฮอล์?\S{0,4}\s*95|(?<!\d)95\s*[-/,]\s*91|(?<!\d)91\s*[-/,]\s*95"),
    ("แก๊สโซฮอล์ 91", r"(แก๊ส)?โซฮอล์?\S{0,4}\s*91|(?<!\d)95\s*[-/,]\s*91|(?<!\d)91\s*[-/,]\s*95"),
    ("แก๊สโซฮอล์", r"แก๊สโซฮอล|โซฮอล"),
    ("เบนซิน", r"เบนซิน"),
    ("LPG", r"LPG|ก๊าซหุงต้ม|แอลพีจี"),
    ("NGV", r"NGV|เอ็นจีวี"),
]
FUEL_RE = [(tag, re.compile(p, re.I)) for tag, p in FUELS]
FUEL_GROUP = {"ดีเซล B20": "diesel", "ดีเซลพรีเมียม": "diesel", "ดีเซล": "diesel", "LPG": "gas", "NGV": "gas"}
EXCEPT_RE = re.compile(r"(ยก)?เว้น\s*(.{0,40})")

_M_ABBR = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
_M_FULL = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน",
           "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
_MONTH_ALT = []
for _i, (_a, _f) in enumerate(zip(_M_ABBR, _M_FULL)):
    _MONTH_ALT.append((_f, _i + 1))
    _MONTH_ALT.append((r"\.?".join(re.escape(c) for c in _a.replace(".", "")) + r"\.?", _i + 1))
_MONTH_ALT.sort(key=lambda x: -len(x[0]))
DATE_TH_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(" + "|".join(f"(?:{p})" for p, _ in _MONTH_ALT) + r")\s*(\d{4}|\d{2})?(?!\d)")
DATE_NUM_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?!\d)")
_MONTH_OF = [(re.compile(p + "$"), m) for p, m in _MONTH_ALT]


def _norm(title: str) -> str:
    t = title.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'")
    for rx, rep in _FIX:
        t = rx.sub(rep, t)
    return t


def _year(y: str | None, mm: int, dd: int, ref: date) -> date | None:
    cands = []
    if y:
        yy = int(y)
        if yy < 100:
            yy += 2500
        if yy > 2400:
            yy -= 543
        cands = [yy]
    else:
        cands = [ref.year - 1, ref.year, ref.year + 1]
    best = None
    for yy in cands:
        try:
            d = date(yy, mm, dd)
        except ValueError:
            continue
        if best is None or abs((d - ref).days) < abs((best - ref).days):
            best = d
    return best


def find_dates(title: str, ref: date) -> list[tuple[int, date]]:
    """All dates in a headline -> [(position, date)], resolving Buddhist-era / missing years."""
    out = []
    for m in DATE_TH_RE.finditer(title):
        mon = next((n for rx, n in _MONTH_OF if rx.match(m.group(2))), None)
        d = _year(m.group(3), mon, int(m.group(1)), ref) if mon else None
        if d:
            out.append((m.start(), d))
    for m in DATE_NUM_RE.finditer(title):
        mm = int(m.group(2))
        if 1 <= mm <= 12:
            d = _year(m.group(3), mm, int(m.group(1)), ref)
            if d:
                out.append((m.start(), d))
    return sorted(out)


def effective_date(title: str, pub_bkk: datetime) -> str:
    ref = pub_bkk.date()
    dates = [(p, d) for p, d in find_dates(title, ref) if -2 <= (d - ref).days <= 4]
    for kw in ("มีผล", "พรุ่งนี้", "เริ่ม"):
        k = title.find(kw)
        if k >= 0:
            after = [d for p, d in dates if 0 <= p - k <= 25]
            if after:
                return after[0].isoformat()
    future = [d for _, d in dates if d >= ref]
    if future:
        return max(future).isoformat()
    if re.search(r"พรุ่งนี้|คืนนี้", title):
        return (ref + timedelta(days=1)).isoformat()
    if re.search(r"วันนี้|เช้านี้", title):
        return ref.isoformat()
    return (ref + timedelta(days=1) if pub_bkk.hour >= 12 else ref).isoformat()


def amounts(title: str) -> list[float]:
    """Price CHANGE amounts in Baht/litre (< 10 Baht; bigger numbers are prices, not changes)."""
    t = title.replace(",", "")
    out = []
    unit_st = r"(?:สตางค์|สต\.?|ส\.\s?ต\.?)"
    for m in re.finditer(r"(\d+)\s*บาท\s*(\d{1,2})\s*" + unit_st, t):
        out.append(int(m.group(1)) + int(m.group(2)) / 100)
    t = re.sub(r"(\d+)\s*บาท\s*(\d{1,2})\s*" + unit_st, " ", t)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*" + unit_st, t):
        v = float(m.group(1))
        out.append(v if v < 1 else v / 100)      # "0.75 สตางค์" is a typo for 0.75 Baht
    t = re.sub(r"(\d+(?:\.\d+)?)\s*" + unit_st, " ", t)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:บาท|บ\.)", t):
        out.append(float(m.group(1)))
    return sorted({round(v, 2) for v in out if 0 < v < 10})


def fuels(title: str) -> tuple[list[str], list[str]]:
    """-> (fuel tags announced, fuel tags explicitly excepted 'ยกเว้น ...')."""
    t = _norm(title)
    exc_txt = ""
    m = EXCEPT_RE.search(t)
    if m:
        exc_txt = m.group(2)
        t = t[: m.start()] + " " + t[m.end():]

    def tags(s: str) -> list[str]:
        found = []
        group_gasoline = bool(re.search(r"กลุ่ม\s*(น้ำมัน)?\s*เบนซิน", s))
        if re.search(r"ทุกชนิด|ทุกประเภท", s):
            found.append("ทุกชนิด")
        if group_gasoline:
            found += ["เบนซิน", "แก๊สโซฮอล์"]
        if re.search(r"กลุ่ม\s*(น้ำมัน)?\s*ดีเซล", s):
            found.append("ดีเซล")
        for tag, rx in FUEL_RE:
            if rx.search(s):
                found.append(tag)
                if tag not in ("แก๊สโซฮอล์ 95", "แก๊สโซฮอล์ 91"):   # these share the "91-95" text
                    s = rx.sub(" ", s)
        specific_gh = any(x.startswith("แก๊สโซฮอล์ ") for x in found)
        if specific_gh and "แก๊สโซฮอล์" in found and not group_gasoline:
            found.remove("แก๊สโซฮอล์")
        order = ["ทุกชนิด"] + [tag for tag, _ in FUELS]
        return sorted(dict.fromkeys(found), key=order.index)

    exc = tags(exc_txt) if exc_txt else []
    return [x for x in tags(t) if x not in exc], exc


def fuel_groups(tags: list[str]) -> list[str]:
    g = set()
    for x in tags:
        if x == "ทุกชนิด":
            g |= {"diesel", "gasoline"}
        else:
            g.add(FUEL_GROUP.get(x, "gasoline"))
    return sorted(g)


def classify(title: str, pub_bkk: datetime) -> dict | None:
    """Headline -> classification, or None if the news is not about retail fuel prices."""
    t = _norm(title)
    if EXCLUDE_RE.search(t) or (MARKET_RE.search(t) and not LOCAL_RE.search(t)):
        return None
    f, exc = fuels(title)
    amt = amounts(t)
    is_adjust = (bool(CHANGE_RE.search(t)) and (bool(amt) or bool(EVIDENCE_RE.search(t)))
                 and (bool(f) or "น้ำมัน" in t))
    if not is_adjust and not DAILY_RE.search(t):
        return None
    up, down, frz = bool(UP_RE.search(t)), bool(DOWN_RE.search(t)), bool(FREEZE_RE.search(t))
    direction = "mixed" if up and down else "up" if up else "down" if down else "freeze" if frz else ""
    return {
        "kind": "adjust" if is_adjust else "daily",
        "template": 1 if TEMPLATE_RE.search(t) else 0,
        "direction": direction if is_adjust else "",
        "fuels": "|".join(f), "except_fuels": "|".join(exc),
        "amounts": "|".join(f"{a:.2f}" for a in amt),
        "effective_date": effective_date(t, pub_bkk),
    }


# ------------------------------------------------------------------ 4. merge into CSV
def load_meta() -> dict:
    try:
        return json.loads(config.NEWS_META.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def merge(existing: list[dict], items: list[dict], now: datetime) -> tuple[list[dict], dict]:
    """Upsert feed items. Keeps first-seen times, never downgrades an exact time to date-only."""
    by_guid = {r["guid"]: dict(r) for r in existing}
    stats = Counter()
    now_s = iso(now)
    for it in items:
        pub_bkk = it["pub"].astimezone(BKK)
        cls = classify(it["title"], pub_bkk)
        old = by_guid.get(it["guid"])
        if cls is None and old is None:
            continue
        base = {"guid": it["guid"], "source_domain": it["source_domain"], "source_name": it["source_name"],
                "title": it["title"], "link": it["link"], "pub_at": iso(pub_bkk),
                "pub_precise": "1" if it["pub_precise"] else "0"}
        if old is None:
            row = {**base, **{k: str(v) for k, v in cls.items()}, "first_seen_at": now_s,
                   "adjust_seen_at": now_s if cls["kind"] == "adjust" else ""}
            by_guid[it["guid"]] = row
            stats["new"] += 1
            stats["new_adjust"] += cls["kind"] == "adjust"
            continue
        row = dict(old)
        if old.get("pub_precise") == "1" and not it["pub_precise"]:
            base["pub_at"], base["pub_precise"] = old["pub_at"], "1"     # keep the exact time we saw earlier
        row.update(base)
        if cls is not None:
            if cls["kind"] == "adjust":
                if old.get("kind") != "adjust":
                    row["adjust_seen_at"] = now_s                       # headline changed into an announcement
                    stats["became_adjust"] += 1
                row.update({k: str(v) for k, v in cls.items()})
            elif old.get("kind") != "adjust":
                row.update({k: str(v) for k, v in cls.items()})
        if any(str(old.get(k, "")) != str(row.get(k, "")) for k in config.NEWS_COLUMNS):
            stats["updated"] += 1
        by_guid[it["guid"]] = row
    # prune price-list articles that never announced a change
    cutoff = (now - timedelta(days=config.NEWS_KEEP_DAILY_DAYS)).astimezone(BKK).isoformat()
    rows = [r for r in by_guid.values() if r.get("kind") == "adjust" or r.get("pub_at", "") >= cutoff]
    stats["pruned"] = len(by_guid) - len(rows)
    rows.sort(key=lambda r: (r.get("pub_at", ""), r["guid"]))
    return rows, dict(stats)


def save(rows: list[dict], now: datetime) -> None:
    write_csv(config.NEWS_CSV, rows, config.NEWS_COLUMNS)
    if not config.NEWS_META.exists():
        config.NEWS_META.write_text(json.dumps({"first_poll_at": iso(now)}, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")


# ------------------------------------------------------------------ 5. timing + events
def reported_time(r: dict, first_poll_at: str) -> tuple[datetime | None, str]:
    """-> (time the site reported the change, basis). basis: pub | seen | unverified | date."""
    pub = parse_iso(r.get("pub_at", ""))
    seen = parse_iso(r.get("adjust_seen_at", "")) or parse_iso(r.get("first_seen_at", ""))
    first_seen = parse_iso(r.get("first_seen_at", ""))
    fp = parse_iso(first_poll_at)
    initial = bool(fp and first_seen and first_seen <= fp + timedelta(minutes=10))
    precise = r.get("pub_precise") == "1"
    if r.get("template") != "1":
        if precise:
            return pub, "pub"
        return (seen, "seen") if seen and not initial else (pub, "date")
    # template article: the headline may have been edited long after pubDate
    if first_seen and seen and seen > first_seen + timedelta(minutes=1):
        return seen, "seen"                       # we watched it change into an announcement
    if initial:
        return pub, "unverified"
    if precise and pub and seen and (seen - pub) <= timedelta(minutes=config.NEWS_TEMPLATE_TRUST_MIN):
        return pub, "pub"
    return seen, "seen"


RANKABLE = {"pub", "seen"}


def _mode(values: list[str]) -> str:
    c = Counter(v for v in values if v)
    return c.most_common(1)[0][0] if c else ""


def build_events(rows: list[dict], first_poll_at: str, since: str | None = None) -> list[dict]:
    """Group price-change news by effective date and rank websites by reporting time."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("kind") != "adjust" or not r.get("effective_date"):
            continue
        if since and r["effective_date"] < since:
            continue
        at, basis = reported_time(r, first_poll_at)
        excluded = is_excluded(r["source_domain"])
        groups[r["effective_date"]].append({**r, "_at": at, "basis": basis if not excluded else "excluded",
                                            "rankable": basis in RANKABLE and not excluded and at is not None})
    events = []
    for eff, items in sorted(groups.items(), reverse=True):
        items.sort(key=lambda x: (not x["rankable"], x["_at"] or datetime.max.replace(tzinfo=BKK)))
        ranked = [x for x in items if x["rankable"]]
        first_at = ranked[0]["_at"] if ranked else None
        per_site: dict[str, dict] = {}
        for x in ranked:                          # earliest article of each site
            per_site.setdefault(x["source_domain"], x)
        rank_times = sorted({x["_at"] for x in per_site.values()})
        sites = []
        for dom, x in per_site.items():
            sites.append({"domain": dom, "name": x["source_name"], "guid": x["guid"], "at": iso(x["_at"]),
                          "basis": x["basis"], "rank": rank_times.index(x["_at"]) + 1,
                          "lag_min": round((x["_at"] - first_at).total_seconds() / 60)})
        sites.sort(key=lambda s: (s["rank"], s["name"]))
        n = len(items)
        tag_count = Counter(t for x in items for t in x.get("fuels", "").split("|") if t)
        order = ["ทุกชนิด"] + [tag for tag, _ in FUELS]
        ev_fuels = sorted((t for t, c in tag_count.items() if c >= max(1, 0.3 * n)), key=order.index)
        dirs = [x.get("direction", "") for x in items]
        direction = _mode([d for d in dirs if d != "mixed"]) or _mode(dirs)
        amt_count = Counter(a for x in items for a in x.get("amounts", "").split("|") if a)
        amt = amt_count.most_common(1)[0][0] if amt_count else ""
        amts = sorted((a for a, c in amt_count.items() if c >= max(1, 0.3 * n)), key=float)
        events.append({
            "effective_date": eff, "direction": direction, "fuels": ev_fuels,
            "groups": fuel_groups(ev_fuels), "except": [t for t, c in Counter(
                t for x in items for t in x.get("except_fuels", "").split("|") if t).most_common(2)],
            "amount": amt, "amounts": amts or ([amt] if amt else []), "first_at": iso(first_at), "first": sites[0] if sites else None,
            "sites": sites, "n_items": n,
            "items": [{"guid": x["guid"], "at": iso(x["_at"]), "basis": x["basis"]} for x in items],
        })
    return events


def ranking(events: list[dict]) -> list[dict]:
    stat: dict[str, dict] = {}
    for ev in events:
        for s in ev["sites"]:
            st = stat.setdefault(s["domain"], {"domain": s["domain"], "name": s["name"], "events": 0, "first": 0,
                                               "top3": 0, "lags": []})
            st["events"] += 1
            st["first"] += s["rank"] == 1
            st["top3"] += s["rank"] <= 3
            st["lags"].append(s["lag_min"])
    out = []
    for st in stat.values():
        lags = st.pop("lags")
        st["median_lag_min"] = round(median(lags)) if lags else None
        st["first_rate"] = round(st["first"] / st["events"], 3) if st["events"] else 0
        out.append(st)
    out.sort(key=lambda s: (-s["first"], -s["top3"], s["median_lag_min"] if s["median_lag_min"] is not None else 1e9,
                            -s["events"], s["name"]))
    for i, s in enumerate(out, 1):
        s["rank"] = i
    return out


def dashboard_block(rows: list[dict] | None = None, meta: dict | None = None, today: str | None = None) -> dict:
    """Everything the dashboard needs (kept small: last NEWS_DASHBOARD_DAYS days)."""
    rows = read_csv(config.NEWS_CSV) if rows is None else rows
    meta = load_meta() if meta is None else meta
    fp = meta.get("first_poll_at", "")
    today = today or config.today_bkk()
    since = (date.fromisoformat(today) - timedelta(days=config.NEWS_DASHBOARD_DAYS)).isoformat()
    events = build_events(rows, fp, since)
    keep = {i["guid"] for ev in events for i in ev["items"]}
    daily_since = (date.fromisoformat(today) - timedelta(days=14)).isoformat()
    items = []
    for r in rows:
        if r["guid"] not in keep and not (r.get("kind") == "daily" and r.get("pub_at", "")[:10] >= daily_since):
            continue
        at, basis = reported_time(r, fp) if r.get("kind") == "adjust" else (parse_iso(r.get("pub_at")), "pub")
        items.append({
            "id": r["guid"], "t": r["title"], "u": safe_link(r["link"]), "s": r["source_domain"],
            "sn": r["source_name"], "pub": r["pub_at"], "pp": r.get("pub_precise") == "1",
            "at": iso(at), "basis": "excluded" if is_excluded(r["source_domain"]) else basis,
            "k": r.get("kind"), "tpl": r.get("template") == "1", "dir": r.get("direction", ""),
            "f": [x for x in r.get("fuels", "").split("|") if x],
            "x": [x for x in r.get("except_fuels", "").split("|") if x],
            "a": [x for x in r.get("amounts", "").split("|") if x], "eff": r.get("effective_date", ""),
        })
    items.sort(key=lambda x: x["at"] or x["pub"], reverse=True)
    return {"first_poll_at": fp, "since": since, "events": events, "ranking": ranking(events), "items": items,
            "excluded_domains": sorted(config.NEWS_EXCLUDE_DOMAINS),
            "template_trust_min": config.NEWS_TEMPLATE_TRUST_MIN}
