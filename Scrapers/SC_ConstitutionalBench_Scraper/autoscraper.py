#!/usr/bin/env python3
"""
Supreme Court Constitutional Bench row-count scraper.
Fetches https://supremecourt.gov.np/web/sam_ijlas and counts the rows
inside the first <table class="table-condensed">. Displays the count in
Nepali and Arabic digits. If the count exceeds BASELINE_ROWS (default 4)
it prints "UPDATE FOUND".
"""
from __future__ import annotations

import argparse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://supremecourt.gov.np/web/sam_ijlas"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
# Baseline known count
BASELINE_ROWS = 4

NEPALI_DIGITS = {
    "0": "०",
    "1": "१",
    "2": "२",
    "3": "३",
    "4": "४",
    "5": "५",
    "6": "६",
    "7": "७",
    "8": "८",
    "9": "९",
}

def to_nepali(num: int) -> str:
    s = str(num)
    for ar, ne in NEPALI_DIGITS.items():
        s = s.replace(ar, ne)
    return s

def row_count() -> int:
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="table-condensed")
    if not table:
        return 0
    return len(table.select("tbody tr"))

def main():
    parser = argparse.ArgumentParser(description="Constitutional Bench row counter")
    args = parser.parse_args()

    try:
        count = row_count()
    except Exception as exc:
        print(f"Error scraping: {exc}")
        return

    print(f"Total constitutional bench items: {to_nepali(count)} ({count})")

    if count > BASELINE_ROWS:
        print("UPDATE FOUND")

if __name__ == "__main__":
    main() 