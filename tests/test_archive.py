"""Offline tests for the 2018 history: EPPO per-brand archive + old structure-file layouts.
Fixtures in tests/fixtures/eppo_old_layouts.json are copied cell-by-cell from real EPPO files
(retail-2018-07-10.xls, pt-price-st-2018-07-19.xls, pt-price-st-2020-10-1.xls, pt-price-st-2018-05-02.xls)."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eppo import archive, build, config, structure  # noqa: E402
import import_seed  # noqa: E402

FX = json.loads((ROOT / "tests" / "fixtures" / "eppo_old_layouts.json").read_text(encoding="utf-8"))


class TestArchiveParser(unittest.TestCase):
    def setUp(self):
        self.rows = archive.parse_grid(FX["archive_2018_07_10"], "retail-2018-07-10.xls")
        self.by = {(r["brand_code"], r["product_code"]): r for r in self.rows}

    def test_all_ten_brands(self):
        self.assertEqual({r["brand_code"] for r in self.rows}, set(config.BRANDS))
        self.assertEqual({r["announce_date"] for r in self.rows}, {"2018-07-10"})

    def test_prices_and_effective_dates(self):
        shell = self.by[("shell", "gh95")]
        self.assertEqual((shell["price"], shell["effective_date"], shell["effective_time"]), (29.85, "2018-06-30", "05:00"))
        self.assertEqual(self.by[("esso", "ds")]["effective_date"], "2018-07-09")
        self.assertEqual(self.by[("pt", "gl95")]["price"], 37.26)
        self.assertEqual(self.by[("susco2", "gh91")]["price"], 29.38)
        self.assertEqual(self.by[("bcp", "pds")]["price"], 32.96)

    def test_zero_means_not_sold(self):
        self.assertEqual(self.by[("irpc", "e20")]["price"], "")
        self.assertTrue(all(r["price"] == "" for r in self.rows if r["product_code"] == "dsb20"))

    def test_year_rollover(self):
        self.assertEqual(archive._effective("28 Dec 05:00", date(2018, 1, 3)), ("2017-12-28", "05:00"))
        self.assertEqual(archive._effective(43108.2083333, date(2018, 1, 9))[0], "2018-01-08")


class TestOldStructureLayouts(unittest.TestCase):
    def test_2018_split_header_and_retail_star(self):
        rows = {r["product_code"]: r for r in structure.parse_grids([FX["structure_2018_07_19"]], "2018-07-19", "x.xls")}
        self.assertEqual(rows["gl95"]["retail"], 36.42)          # label 'ULG'
        self.assertEqual(rows["ds"]["retail"], 28.59)            # 'H-DIESEL' = B7 in 2018
        self.assertEqual(rows["gh95"]["oil_fund"], 0.72)         # 'OIL' / 'FUND' on two rows
        self.assertEqual(rows["gh95"]["excise_tax"], 5.85)       # 'TAX'
        self.assertEqual(rows["gh95"]["vat_wholesale"], 1.76)    # first VAT
        self.assertEqual(rows["gh95"]["vat_marketing_margin"], 0.15)  # second VAT
        self.assertEqual(rows["lpg"]["retail"], 21.87)
        self.assertEqual(rows["gh95"]["fx_thb_usd"], 33.51)

    def test_2020_h_diesel_is_b10_when_b7_row_exists(self):
        rows = {r["product_code"]: r["retail"] for r in structure.parse_grids([FX["structure_2020_10_01"]], "2020-10-01")}
        self.assertEqual(rows["ds"], 21.59)
        self.assertEqual(rows["dsb10"], 18.59)
        self.assertEqual(rows["dsb20"], 18.34)

    def test_report_sheet_before_structure_sheet(self):
        report = [["รายงานราคาน้ำมันเชื้อเพลิง"], ["ทาปิส", "", 85.37]]
        rows = structure.parse_grids([report, FX["structure_2020_10_01"]], "2020-10-01")
        self.assertIn("gl95", {r["product_code"] for r in rows})

    def test_file_without_retail_column(self):
        with self.assertRaises(ValueError):
            structure.parse_grids([FX["structure_2018_05_02_no_retail"]], "2018-05-02")


def arow(ad, b, p, price, eff):
    return {"announce_date": ad, "brand_code": b, "product_code": p, "price": price,
            "effective_date": eff if price != "" else "", "effective_time": "05:00", "source_file": "t"}


class TestArchiveInBuild(unittest.TestCase):
    def test_carry_until_archive_end_then_gap(self):
        arch = [arow("2018-06-30", "bcp", "gh95", 29.25, "2018-06-30"),
                arow("2018-07-07", "bcp", "gh95", 29.65, "2018-07-07"),
                arow("2018-07-10", "bcp", "gh95", 29.65, "2018-07-07")]
        api_rows = [{"snapshot_date": "2026-09-24", "brand_code": "bcp", "product_code": "gh95", "price": "39.94",
                     "effective_date": "2026-09-24", "effective_time": "05:00"}]
        daily = build.build_daily(api_rows, [], "2026-09-25", archive_rows=arch)
        got = {r["date"]: r["price"] for r in daily}
        self.assertEqual(got["2018-07-06"], 29.25)
        self.assertEqual(got["2018-07-07"], 29.65)
        self.assertEqual(got["2018-07-10"], 29.65)
        self.assertNotIn("2018-07-11", got)          # archive ended: no invented prices
        self.assertNotIn("2020-01-01", got)
        self.assertEqual(got["2026-09-24"], 39.94)

    def test_not_sold_any_more_stops_series(self):
        arch = [arow("2018-01-09", "shell", "e85", 21.0, "2018-01-09"),
                arow("2018-02-01", "shell", "e85", "", ""),
                arow("2018-02-01", "shell", "gh95", 28.0, "2018-02-01")]
        daily = build.build_daily([], [], "2018-02-05", archive_rows=arch)
        e85 = {r["date"] for r in daily if r["product_code"] == "e85"}
        self.assertIn("2018-01-31", e85)
        self.assertNotIn("2018-02-01", e85)

    def test_structure_beats_archive_for_ptt(self):
        arch = [arow("2018-03-01", "ptt", "gh95", 27.85, "2018-03-01"),
                arow("2018-03-22", "ptt", "gh95", 27.75, "2018-03-22")]   # archive missed the 6 Mar cut
        st = [{"date": "2018-03-06", "product_code": "gh95", "retail": "27.35", "source_file": "pt-price-st-2018-03-06.xls"}]
        daily = build.build_daily([], st, "2018-03-08", archive_rows=arch)
        got = {r["date"]: (r["price"], r["source"]) for r in daily}
        self.assertEqual(got["2018-03-05"], (27.85, "carried_forward"))
        self.assertEqual(got["2018-03-06"], (27.35, "eppo_structure"))
        self.assertEqual(got["2018-03-08"][0], 27.35)

    def test_history_start_clamp(self):
        arch = [arow("2017-12-30", "pure", "ds", 27.19, "2017-12-30"), arow("2018-01-09", "pure", "ds", 27.59, "2018-01-09")]
        daily = build.build_daily([], [], "2018-01-10", archive_rows=arch)
        self.assertEqual(min(r["date"] for r in daily), config.HISTORY_START)
        self.assertEqual({r["date"]: r["price"] for r in daily}["2018-01-01"], 27.19)


class TestSeeds(unittest.TestCase):
    def test_archive_seed(self):
        rows = import_seed.expand_archive_txt(ROOT / "data" / "seed" / "archive_retail_2018.txt")
        self.assertEqual(len({r["announce_date"] for r in rows}), 32)
        by = {(r["announce_date"], r["brand_code"], r["product_code"]): r for r in rows}
        self.assertEqual(by[("2018-07-10", "shell", "gh95")]["price"], 29.85)
        self.assertEqual(by[("2018-07-10", "shell", "gh95")]["effective_date"], "2018-06-30")
        self.assertEqual(by[("2018-05-17", "irpc", "gh95")]["effective_time"], "09:06")

    def test_structure_seed(self):
        rows = import_seed.expand_structure_txt(ROOT / "data" / "seed" / "structure_retail_2018_2024.txt")
        by = {(r["date"], r["product_code"]): r["retail"] for r in rows}
        self.assertEqual(by[("2018-07-19", "gl95")], 36.42)      # = fixture pt-price-st-2018-07-19
        self.assertEqual(by[("2020-10-01", "dsb10")], 18.59)     # = fixture pt-price-st-2020-10-1
        self.assertEqual(by[("2020-10-01", "ds")], 21.59)
        self.assertNotIn(("2019-07-15", "gh95"), by)             # EPPO has no files for July 2019


if __name__ == "__main__":
    unittest.main()
