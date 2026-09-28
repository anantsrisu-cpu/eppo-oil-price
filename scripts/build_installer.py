#!/usr/bin/env python3
"""Build the one-file setup wizard  dist/ติดตั้งระบบ-EPPO.html

It embeds every file of this repository (except build output, caches and PDFs) so a
non-developer can install the whole system on GitHub from a web page:
  python scripts/build_installer.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.0.0"
SKIP_DIRS = {"_site", "__pycache__", ".git", "dist", ".venv", "venv"}
SKIP_SUFFIX = {".pyc", ".pdf", ".sqlite", ".tmp"}


def collect() -> list[dict]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if not p.is_file() or any(part in SKIP_DIRS for part in rel.parts) or p.suffix in SKIP_SUFFIX:
            continue
        out.append({"path": rel.as_posix(), "b64": base64.b64encode(p.read_bytes()).decode()})
    return out


def main() -> int:
    files = collect()
    must = {".github/workflows/daily-update.yml", ".github/workflows/ci.yml", "scripts/fetch_daily.py",
            "requirements.txt", "site/index.html"}
    missing = must - {f["path"] for f in files}
    if missing:
        sys.exit(f"missing files: {missing}")
    tpl = (ROOT / "installer" / "template.html").read_text(encoding="utf-8")
    html = (tpl.replace("__FILES__", json.dumps(files, separators=(",", ":")))
               .replace("__VERSION__", VERSION).replace("__FILECOUNT__", str(len(files))))
    out = ROOT / "dist" / "ติดตั้งระบบ-EPPO.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{out} ({len(files)} files, {out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
