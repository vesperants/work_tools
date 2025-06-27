#!/usr/bin/env python3
"""
Law Commission Nepal Auto-Scraper

This script checks the "मौजुदा कानून" category page for newly uploaded files.
If files newer than the date stored in ``last_update.txt`` are found,
their names and dates are printed to the terminal.

Usage::

    python autoscraper.py           # one-off run
    python autoscraper.py --update  # run and, if newer files exist, update last_update.txt

Dependencies: requests, beautifulsoup4

The script works entirely in Bikram Sambat (BS) and Nepali numerals – it does **not**
convert to Gregorian dates; it simply converts Nepali numerals and month names to
integers so they can be compared.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import List, Tuple

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://lawcommission.gov.np/category/1806/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Mapping of Nepali digits to Arabic digits
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

# Mapping of Nepali month names to month numbers (Bikram Sambat)
NEPALI_MONTHS = {
    "बैशाख": 1,
    "वैशाख": 1,
    "जेठ": 2,
    "जेष्ठ": 2,
    "असार": 3,
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
}

# Reverse mapping to retrieve a representative Nepali month name for display
_NUM_TO_MONTH = {v: k for k, v in NEPALI_MONTHS.items()}


def _month_name_from_num(num: int) -> str:
    """Return Nepali month name for *num* (1-12)."""
    return _NUM_TO_MONTH.get(num, "")


LAST_UPDATE_FILE = Path(__file__).with_name("last_update.txt")


class NepaliDate:
    """Simple representation of a BS date; comparable using Y-M-D ordering."""

    __slots__ = ("year", "month", "day")

    def __init__(self, year: int, month: int, day: int):
        self.year = year
        self.month = month
        self.day = day

    def __lt__(self, other: "NepaliDate") -> bool:  # type: ignore[override]
        return (self.year, self.month, self.day) < (other.year, other.month, other.day)

    def __eq__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, NepaliDate):
            return NotImplemented
        return (self.year, self.month, self.day) == (
            other.year,
            other.month,
            other.day,
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"NepaliDate({self.year}, {self.month}, {self.day})"

    def __str__(self) -> str:  # pragma: no cover
        # Convert back to Nepali numerals for display
        year = _to_nepali_numerals(str(self.year))
        month_name = _month_name_from_num(self.month)
        day = _to_nepali_numerals(f"{self.day}")
        return f"{day} {month_name}, {year}"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _from_nepali_numerals(text: str) -> str:
    """Convert Nepali digits in *text* to ASCII digits."""
    for nd, ad in NEPALI_DIGITS.items():
        text = text.replace(nd, ad)
    return text


def _to_nepali_numerals(text: str) -> str:
    """Convert ASCII digits in *text* to Nepali digits (for printing)."""
    for nd, ad in NEPALI_DIGITS.items():
        text = text.replace(ad, nd)
    return text


def parse_nepali_date(date_str: str) -> NepaliDate:
    """Parse a date string like '२ जेठ, २०८२' -> NepaliDate(2082, 2, 2)."""
    # Remove commas and extra whitespace
    cleaned = re.sub(r"[,\s]+", " ", date_str.strip())

    # Expected pattern: <day> <month> <year>
    m = re.match(r"([०१२३४५६७८९]+)\s+([^\s]+)\s+([०१२३४५६७८९]+)", cleaned)
    if not m:
        raise ValueError(f"Unrecognised date format: {date_str!r}")

    day_nep, month_nep, year_nep = m.groups()
    day = int(_from_nepali_numerals(day_nep))
    year = int(_from_nepali_numerals(year_nep))

    month = NEPALI_MONTHS.get(month_nep)
    if month is None:
        raise ValueError(f"Unknown Nepali month name: {month_nep!r}")

    return NepaliDate(year, month, day)


def read_last_update() -> NepaliDate:
    if not LAST_UPDATE_FILE.exists():
        raise FileNotFoundError(
            f"{LAST_UPDATE_FILE} not found – create it with an initial date in Nepali, e.g. '२० फागुन, २०८१'"
        )
    raw = LAST_UPDATE_FILE.read_text(encoding="utf-8").strip()
    return parse_nepali_date(raw)


def write_last_update(date: NepaliDate) -> None:
    LAST_UPDATE_FILE.write_text(str(date), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core scraping logic
# ---------------------------------------------------------------------------


def fetch_page(page: int | None = None) -> str:
    url = BASE_URL if page in (None, 1) else f"{BASE_URL}?page={page}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def extract_cards(html: str) -> List[Tuple[str, NepaliDate]]:
    """Return list of (title, date) pairs from one page."""
    soup = BeautifulSoup(html, "html.parser")
    cards: List[Tuple[str, NepaliDate]] = []

    for card in soup.select("div.grid__card"):
        # title text
        title_tag = card.select_one("h3.card__title a")
        date_tag = card.select_one("div.post__date p")
        if not title_tag or not date_tag:
            continue  # skip malformed cards

        title = title_tag.get_text(strip=True)
        date_text = date_tag.get_text(strip=True)

        try:
            date = parse_nepali_date(date_text)
        except Exception:
            # Skip cards with unrecognisable dates – safer than failing outright
            continue

        cards.append((title, date))

    return cards


def collect_new_files(last_update: NepaliDate, max_pages: int = 10) -> List[Tuple[str, NepaliDate]]:
    """Scan pages until we encounter a date older than or equal to *last_update*.

    Returns a list of (title, date) pairs that are newer than *last_update*.
    """
    new_files: List[Tuple[str, NepaliDate]] = []

    for page in range(1, max_pages + 1):
        html = fetch_page(page)
        cards = extract_cards(html)
        if not cards:
            break  # no more cards; stop early

        for title, date in cards:
            if date > last_update:
                new_files.append((title, date))
            else:
                # As soon as we hit an old/ equal date, we assume the rest are older and can stop
                return new_files

    return new_files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Law Commission Nepal site for new uploads.")
    parser.add_argument(
        "--update",
        action="store_true",
        help="If new files are found, overwrite last_update.txt with the most recent date found.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Maximum number of pages to scan (default: 5).",
    )

    args = parser.parse_args()

    try:
        last_update = read_last_update()
    except Exception as exc:
        print(f"Error reading last_update.txt: {exc}")
        return

    print(f"Last recorded update: {last_update}")

    try:
        new_files = collect_new_files(last_update, max_pages=args.pages)
    except Exception as exc:
        print(f"Error while scraping: {exc}")
        return

    if not new_files:
        print("No new updates found.")
        return

    # Terminal alert
    print("UPDATE FOUND")

    print("\nNew files detected:")
    for title, date in new_files:
        print(f"- {title} (Date: {date})")

    most_recent_date = max(date for _, date in new_files)

    if args.update:
        write_last_update(most_recent_date)
        print(f"\nlast_update.txt updated to: {most_recent_date}")
    else:
        print("\nRun with --update to record this date as the new last_update.")


if __name__ == "__main__":
    main() 