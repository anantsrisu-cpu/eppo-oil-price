"""Offline tests for the online-news module (no network).

Fixture tests/fixtures/google_news_oil.xml = real Google News headlines captured on 5 Nov 2026
(the 0.70 Baht cut of petrol/gasohol effective 5 Nov 2026, plus off-topic news that must be ignored).
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eppo import build, config, news  # noqa: E402
from eppo.http import _check_url  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "google_news_oil.xml"
BKK = config.TZ_BKK


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=BKK)


def cls(title: str, pub: str = "2026-11-04T19:00"):
    return news.classify(title, at(pub))


def rss(*items: tuple[str, str, str, str]) -> bytes:
    """items = (guid, pubDate, source url, title)"""
    body = "".join(
        f'<item><title>{t}</title><link>https://news.google.com/rss/articles/{g}?oc=5</link>'
        f'<guid isPermaLink="false">{g}</guid><pubDate>{p}</pubDate><source url="{u}">src</source></item>'
        for g, p, u, t in items)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>{body}</channel></rss>'.encode()


class TestFeed(unittest.TestCase):
    def setUp(self):
        self.items = news.parse_rss(FIXTURE.read_bytes())

    def test_parse_fixture(self):
        self.assertEqual(len(self.items), 36)
        mgr = next(i for i in self.items if i["source_domain"] == "mgronline.com")
        self.assertEqual(mgr["source_name"], "ผู้จัดการออนไลน์")
        self.assertFalse(mgr["title"].endswith("ผู้จัดการออนไลน์"))       # " - <source>" suffix removed
        self.assertTrue(mgr["link"].startswith("https://news.google.com/"))
        self.assertEqual(mgr["pub"].astimezone(BKK).strftime("%Y-%m-%d %H:%M"), "2026-11-04 19:04")
        self.assertTrue(mgr["pub_precise"])
        kh = next(i for i in self.items if i["source_domain"] == "khaosod.co.th")
        self.assertFalse(kh["pub_precise"])                                 # 07:00:00 GMT = date only

    def test_refuses_dtd_and_bad_links(self):
        with self.assertRaises(ValueError):
            news.parse_rss(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss><channel/></rss>')
        bad = rss(("g1", "Wed, 04 Nov 2026 12:00:00 GMT", "https://www.thairath.co.th", "ลดราคา 50 สต. มีผลพรุ่งนี้"))
        bad = bad.replace(b"https://news.google.com/rss/articles/g1?oc=5", b"javascript:alert(1)")
        self.assertEqual(news.parse_rss(bad), [])
        for u in ("javascript:alert(1)", "http://x.com/", "https://a.com/x\"onmouseover=1", ""):
            self.assertEqual(news.safe_link(u), "")
        self.assertEqual(news.safe_link("https://news.google.com/rss/articles/abc?oc=5"),
                         "https://news.google.com/rss/articles/abc?oc=5")

    def test_allow_list(self):
        _check_url(news.feed_url("ราคาน้ำมัน when:2d"))
        with self.assertRaises(ValueError):
            _check_url("https://news.google.com.evil.example/rss")


class TestClassify(unittest.TestCase):
    def test_announcement(self):
        c = cls("กบน. หั่นราคากลุ่มเบนซิน 0.70 บาท มีผล 5 พ.ย. นี้ ยกเว้น E85")
        self.assertEqual((c["kind"], c["direction"], c["amounts"], c["effective_date"]),
                         ("adjust", "down", "0.70", "2026-11-05"))
        self.assertEqual(c["fuels"], "แก๊สโซฮอล์|เบนซิน")
        self.assertEqual(c["except_fuels"], "แก๊สโซฮอล์ E85")
        self.assertEqual(c["template"], 0)

    def test_up_and_amount_formats(self):
        c = cls("เติมด่วน! OR-PTG ขึ้นราคาน้ำมัน 60 สต. ดีเซลแตะ 43.54 บาท มีผลพรุ่งนี้", "2026-10-20T18:00")
        self.assertEqual((c["direction"], c["amounts"], c["effective_date"]), ("up", "0.60", "2026-10-21"))
        self.assertEqual(news.amounts("ลดดีเซล B20 ลง 3 บาท 69 สตางค์"), [3.69])
        self.assertEqual(news.amounts("ลง 70สต./ลิตร"), [0.70])
        self.assertEqual(news.amounts("ปรับขึ้นทุกชนิด 0.75 สตางค์ต่อลิตร"), [0.75])   # common typo
        self.assertEqual(news.amounts("ดีเซลแตะ 43.54 บาท"), [])                       # a price, not a change

    def test_off_topic_is_ignored(self):
        for t in ("ม็อบรถบรรทุกเรียกร้องตรึงราคาดีเซล 35 บาทต่อลิตร",
                  "สหพันธ์ขนส่งฯ บุกพลังงาน จี้ตรึงดีเซล 35 บาท 1 ปี",
                  "ราคาน้ำมันโลกร่วงหนักกว่า 8% WTI หลุด 90 เหรียญ",
                  "เจาะต้นทุนราคาน้ำมันไทย 4 พ.ย. 69 เบนซิน-ดีเซลหน้าโรงกลั่น 25.14-35.58 บาท/ลิตร",
                  "น้ำมันแพงเป็นเหตุ รถเกี่ยวข้าวปรับขึ้นไร่ละ 100 บาท",
                  "ลดภาษีน้ำมันพยุงราคา B20-E20 หลังกองทุนติดลบหนักแสนล้าน"):
            self.assertIsNone(cls(t), t)

    def test_world_market_words_with_local_announcement_kept(self):
        c = cls("ข่าวดีคนมีรถ! กบน. ปรับลดราคาแก๊สโซฮอล์ 70 สต./ลิตร มีผล 5 พ.ย. 69 ขานรับราคาน้ำมันตลาดโลกชะลอตัว")
        self.assertEqual(c["kind"], "adjust")

    def test_daily_price_list_and_template(self):
        c = cls("ราคาน้ำมันพรุ่งนี้2569 (4 พ.ย. 69) ปตท. บางจาก อัปเดตราคาล่าสุด", "2026-11-03T17:00")
        self.assertEqual((c["kind"], c["template"], c["effective_date"]), ("daily", 1, "2026-11-04"))
        c = cls("ราคาน้ำมันพรุ่งนี้2569 (5 พ.ย. 69) ปตท. บางจากลดราคาเบนซิน แก๊สโซฮอล์ 70 สตางค์", "2026-11-04T17:00")
        self.assertEqual((c["kind"], c["template"], c["direction"]), ("adjust", 1, "down"))

    def test_effective_dates(self):
        self.assertEqual(news.effective_date("อัปเดตราคาน้ำมันล่าสุดวันนี้ 04/11/69 พรุ่งนี้ 05/11/69 ปรับลด",
                                             at("2026-11-04T21:00")), "2026-11-05")
        self.assertEqual(news.effective_date("กบน. ประกาศปรับลดราคาน้ำมัน มีผลเช้าวันนี้", at("2026-11-05T07:22")),
                         "2026-11-05")
        self.assertEqual(news.effective_date("ปรับขึ้นราคา มีผล 1 ม.ค.", at("2026-12-31T18:00")), "2027-01-01")


class TestMergeAndRanking(unittest.TestCase):
    def test_fixture_events(self):
        items = news.parse_rss(FIXTURE.read_bytes())
        first = at("2026-11-05T08:00")
        rows, stats = news.merge([], items, first)
        self.assertEqual(stats["new_adjust"], 24)
        ev = news.build_events(rows, news.iso(first))[0]
        self.assertEqual(ev["effective_date"], "2026-11-05")
        self.assertEqual(ev["direction"], "down")
        self.assertEqual((ev["first"]["name"], ev["first"]["at"]), ("ผู้จัดการออนไลน์", "2026-11-04T19:04+07:00"))
        self.assertEqual([s["name"] for s in ev["sites"][:3]], ["ผู้จัดการออนไลน์", "ประชาชาติธุรกิจ", "โพสต์ทูเดย์"])
        self.assertEqual(ev["sites"][1]["lag_min"], 5)
        bases = {i["guid"]: i["basis"] for i in ev["items"]}
        dom = {r["guid"]: r["source_domain"] for r in rows}
        # aggregator never ranked; template article seen only on the first run cannot be timed
        self.assertTrue(all(b == "excluded" for g, b in bases.items() if dom[g] == "th.headtopics.com"))
        self.assertIn("unverified", bases.values())
        self.assertNotIn("pptvhd36.com", [s["domain"] for s in ev["sites"]])
        rk = news.ranking(news.build_events(rows, news.iso(first)))
        self.assertEqual(rk[0]["domain"], "mgronline.com")

    def test_aggregator_only_date_is_not_an_event(self):
        feed = rss(("h1", "Wed, 04 Nov 2026 12:53:00 GMT", "https://th.headtopics.com",
                    "ปรับลดราคาน้ำมันแก๊สโซฮอล์ ยกเว้น E85 ลิตรละ 0.7 บาท มีผล 4 พ.ย. 2569"),
                   ("p1", "Wed, 04 Nov 2026 12:09:00 GMT", "https://www.prachachat.net",
                    "กบน. เคาะลดราคาน้ำมันกลุ่มเบนซิน 70 สต. ยกเว้น E85 มีผล 5 พ.ย. 69"))
        t0 = at("2026-11-05T08:00")
        rows, _ = news.merge([], news.parse_rss(feed), t0)
        self.assertEqual([e["effective_date"] for e in news.build_events(rows, news.iso(t0))], ["2026-11-05"])

    def test_template_title_change_uses_time_we_saw_it(self):
        guid = "tpl1"
        p1 = rss((guid, "Wed, 04 Nov 2026 10:00:00 GMT", "https://www.thansettakij.com",
                  "ราคาน้ำมันพรุ่งนี้2569 (5 พ.ย. 69) ปตท. บางจาก อัปเดตราคาล่าสุด"),
                 ("other", "Wed, 04 Nov 2026 12:09:00 GMT", "https://www.prachachat.net",
                  "กบน. เคาะลดราคาน้ำมันกลุ่มเบนซิน 70 สต. ยกเว้น E85 มีผล 5 พ.ย. 69"))
        p2 = rss((guid, "Wed, 04 Nov 2026 10:00:00 GMT", "https://www.thansettakij.com",
                  "ราคาน้ำมันพรุ่งนี้2569 (5 พ.ย. 69) ปตท. บางจากลดราคาเบนซิน แก๊สโซฮอล์ 70 สตางค์"))
        t0, t1, t2 = at("2026-11-04T08:00"), at("2026-11-04T17:20"), at("2026-11-04T19:40")
        rows, _ = news.merge([], [], t0)                       # first poll (nothing yet)
        rows, s1 = news.merge(rows, news.parse_rss(p1), t1)
        self.assertEqual(s1["new"], 2)
        rows, s2 = news.merge(rows, news.parse_rss(p2), t2)
        self.assertEqual(s2["became_adjust"], 1)
        r = next(x for x in rows if x["guid"] == guid)
        when, basis = news.reported_time(r, news.iso(t0))
        self.assertEqual((news.iso(when), basis), ("2026-11-04T19:40+07:00", "seen"))   # not 17:00 pubDate
        ev = news.build_events(rows, news.iso(t0))[0]
        self.assertEqual(ev["first"]["domain"], "prachachat.net")

    def test_exact_time_not_downgraded_and_old_lists_pruned(self):
        g = "x1"
        exact = rss((g, "Wed, 04 Nov 2026 12:09:00 GMT", "https://www.prachachat.net",
                     "กบน. เคาะลดราคาน้ำมัน 70 สต. มีผล 5 พ.ย. 69"))
        dateonly = exact.replace(b"12:09:00", b"07:00:00")
        rows, _ = news.merge([], news.parse_rss(exact), at("2026-11-04T19:30"))
        rows, _ = news.merge(rows, news.parse_rss(dateonly), at("2026-11-08T10:00"))
        self.assertEqual((rows[0]["pub_at"], rows[0]["pub_precise"]), ("2026-11-04T19:09+07:00", "1"))
        old = rss(("d1", "Mon, 01 Jun 2026 03:00:00 GMT", "https://www.sanook.com",
                   "อัปเดต ราคาน้ำมันวันนี้ 1/6/2569 ลิตรละกี่บาท"))
        rows, st = news.merge(rows, news.parse_rss(old), at("2026-11-08T10:00"))
        self.assertEqual(st.get("pruned"), 1)
        self.assertEqual([r["guid"] for r in rows], [g])

    def test_build_tables(self):
        items = news.parse_rss(FIXTURE.read_bytes())
        first = at("2026-11-05T08:00")
        rows, _ = news.merge([], items, first)
        nb = news.dashboard_block(rows, {"first_poll_at": news.iso(first)}, today="2026-11-05")
        con = sqlite3.connect(":memory:")
        con.executescript(build.SCHEMA)
        build.add_news(con, rows, nb)
        top = con.execute("SELECT source_domain, times_first FROM v_news_fastest LIMIT 1").fetchone()
        self.assertEqual(top, ("mgronline.com", 1))
        piv = build.news_pivots(nb, rows)
        self.assertEqual(piv["news_events"][1][0][5], "ผู้จัดการออนไลน์")
        self.assertTrue(all(i["u"].startswith("https://") for i in nb["items"]))
        con.close()


if __name__ == "__main__":
    unittest.main()
