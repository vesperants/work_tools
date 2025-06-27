#!/usr/bin/env python3
"""
Supreme Court Bulletin Auto-Scraper

Checks the "Latest Bulletins" table for new PDF entries and prints them.

Comparison order:
    (year, month, volume, issue)

If any row is newer than the tuple stored in ``last_update.txt`` a list is
printed. Optional --update flag writes the most-recent tuple back to file.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://supremecourt.gov.np/web/bulletin"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Nepali digits to Arabic
NEPALI_DIGITS = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
}

NEPALI_MONTHS = {
    "बैशाख": 1,
    "वैशाख": 1,
    "जेठ": 2,
    "जेष्ठ": 2,
    "असार": 3,
    "आसार": 3,
    "साउन": 4,
    "श्रावण": 4,
    "भदौ": 5,
    "भाद्र": 5,
    "असोज": 6,
    "आश्विन": 6,
    "अश्विन": 6,
    "कार्तिक": 7,
    "कात्तिक": 7,
    "मंसिर": 8,
    "पुष": 9,
    "पुस": 9,
    "माघ": 10,
    "फाल्गुन": 11,
    "फागुन": 11,
    "चैत": 12,
    "चैत्र": 12,
}

_NUM_TO_MONTH = {v: k for k, v in NEPALI_MONTHS.items()}

LAST_UPDATE_FILE = Path(__file__).with_name("last_update.txt")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _from_nepali_digits(text: str) -> str:
    for nd, ad in NEPALI_DIGITS.items():
        text = text.replace(nd, ad)
    return text


def _to_nepali_digits(text: str) -> str:
    for nd, ad in NEPALI_DIGITS.items():
        text = text.replace(ad, nd)
    return text


def _month_to_num(month: str) -> int:
    num = NEPALI_MONTHS.get(month.strip())
    if num is None:
        raise ValueError(f"Unknown Nepali month name: {month}")
    return num


def _num_to_month(num: int) -> str:
    return _NUM_TO_MONTH.get(num, "")


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------


def fetch_page() -> str:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def extract_entries(html: str) -> List[Tuple[BulletinEntry, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-striped")
    if not table:
        return []
    entries: List[Tuple[BulletinEntry, str]] = []
    for tr in table.select("tbody tr"):
        tds = [td.get_text(strip=True).replace("\xa0", " ") for td in tr.find_all("td")]
        if len(tds) < 6:
            continue  # malformed row
        year_text, month_text, volume_text, issue_text = (
            tds[1],
            tds[2],
            tds[3],
            tds[4],
        )
        try:
            entry = BulletinEntry(
                int(_from_nepali_digits(year_text)),
                _month_to_num(month_text),
                int(_from_nepali_digits(volume_text)),
                int(_from_nepali_digits(issue_text)),
            )
        except Exception:
            continue
        # pdf link
        link_tag = tr.find("a", href=True)
        pdf_url: Optional[str] = link_tag["href"].strip() if link_tag else None
        entries.append((entry, pdf_url or ""))
    return entries


def get_row_count() -> int:
    """Return total number of bulletin rows in the table."""
    html = fetch_page()
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-striped")
    if not table:
        return 0
    return len(table.select("tbody tr"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Print current maximum bulletin serial number.")
    args = parser.parse_args()

    try:
        row_count = get_row_count()
    except Exception as exc:
        print(f"Error scraping: {exc}")
        return

    nep_count = _to_nepali_digits(str(row_count))
    print(f"Total bulletins listed: {nep_count} ({row_count})")


if __name__ == "__main__":
    main() 