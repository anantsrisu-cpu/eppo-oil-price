#!/usr/bin/env python3
"""Rebuild SQLite, pivot CSV/Excel, dashboard JSON and daily report from data/*.csv
(no network access). Run after editing data by hand, or to preview locally:

  python scripts/build_outputs.py
  python -m http.server 8000 --directory _site      # then open http://localhost:8000
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eppo import build  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(build.run())
