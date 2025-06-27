#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_cons_panel.py
────────────────────
Scan the current directory for *.html files and build Cons_panel.csv with:

    • file_name        (base name, no “.html”)
    • html             (raw HTML content)
    • text_normalized  (plain text stripped from HTML and normalised)

Drop this script in the same folder as the bulletin_*.html files and run:

    python3 create_cons_panel.py
"""

from __future__ import annotations

import csv
import html as html_lib
import os
import re
import sys
from pathlib import Path


###############################################################################
# 1.  Nepali normalisation rules
###############################################################################
def normalize_nepali_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    # Rule 1 – drop Nukta
    text = text.replace("़", "")
    # Rule 2 – drop ZWJ (​\u200d)
    text = text.replace("\u200d", "")

    # Rule 3 – unify sibilants
    text = text.replace("श", "स").replace("ष", "स")

    # Rule 4 – long → short vowels (incl. matras)
    long_to_short = {
        "ई": "इ", "ऊ": "उ", "ऐ": "ए", "औ": "ओ",
        "ी": "ि", "ू": "ु", "ै": "े", "ौ": "ो",
    }
    for long_v, short_v in long_to_short.items():
        text = text.replace(long_v, short_v)

    # Rule 5 – chandrabindu → anusvara
    text = text.replace("ँ", "ं")

    # Rule 6 – drop visarga
    text = text.replace("ः", "")
    return text


###############################################################################
# 2.  Minimal HTML → plain-text helper (std-lib only)
###############################################################################
_HTML_TAG_RE     = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(?:script|style)[^>]*>.*?</(?:script|style)>",
                               flags=re.I | re.S)


def html_to_text(raw_html: str) -> str:
    """Strip tags / scripts / entities and collapse whitespace."""
    if not isinstance(raw_html, str):
        return ""
    txt = _SCRIPT_STYLE_RE.sub(" ", raw_html)   # drop <script>/<style> blocks
    txt = _HTML_TAG_RE.sub(" ", txt)            # remove remaining tags
    txt = html_lib.unescape(txt)                # &nbsp; etc.
    txt = re.sub(r"\s+", " ", txt).strip()      # collapse WS
    return txt


###############################################################################
# 3.  Main processing routine
###############################################################################
def process_html_files(directory: Path = Path(".")) -> list[dict]:
    rows: list[dict] = []
    csv.field_size_limit(sys.maxsize)           # allow very large fields

    for html_file in sorted(directory.glob("*.html")):
        try:
            raw_html = html_file.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"⚠️  Skipping {html_file.name}: {exc}")
            continue

        plain_text       = html_to_text(raw_html)
        normalized_text  = normalize_nepali_text(plain_text)

        rows.append({
            "file_name":       html_file.stem,
            "html":            raw_html,
            "text_normalized": normalized_text,
        })
        print(f"✓  processed {html_file.name}")

    return rows


def write_csv(rows: list[dict], out_path: Path = Path("Cons_panel.csv")) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(
            fout,
            fieldnames=["file_name", "html", "text_normalized"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅  {out_path.name} written with {len(rows)} rows.")


###############################################################################
# 4.  Entrypoint
###############################################################################
def main() -> None:
    rows = process_html_files(Path("."))
    if not rows:
        print("No HTML files found – nothing to do.")
        return
    write_csv(rows)


if __name__ == "__main__":
    main()