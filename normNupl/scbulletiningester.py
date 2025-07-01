#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_sc_bulletin.py
─────────────────────
Bulk-loads  SC_Bulletins_norm.csv  into a new index  sc_bulletin.

• Deletes / recreates the index each run
• Accepts Date in YYYY/MM/DD, YYYY/MM, YYYY-MM-DD, or YYYY-MM
• Uses SigV4 auth (same as ingest_multi_reset.py)
• Checkpoint + retry logic identical to your other loaders
"""

from __future__ import annotations
import csv, json, sys, logging, re, itertools, pathlib, hashlib, traceback
from datetime import datetime
from typing import Dict, List, Iterable, Tuple

# ─── OpenSearch / AWS imports for SigV4 ───────────────────
import boto3
from opensearchpy import OpenSearch, helpers, RequestsHttpConnection, AWSV4SignerAuth
from tqdm import tqdm
from logging.handlers import RotatingFileHandler

# ─────────────────────  CONFIG  ───────────────────────────
HOST   = "search-stirsat-vhuxip6bjql4c2iahjpkfqjc6i.eu-north-1.es.amazonaws.com"
REGION = "eu-north-1"
AWS_ACCESS_KEY_ID     = ""
AWS_SECRET_ACCESS_KEY = ""

INDEX  = "sc_bulletin"
CSV_IN = "SC_Bulletins_norm.csv"

BATCH_DOCS  = 100
BATCH_BYTES = 8 * 1024 * 1024    # <10 MB
REQ_TIMEOUT = 60                 # seconds

CKPT_FILE = pathlib.Path(".sc_bulletin_ingest.ckpt")
FAIL_FILE = "failed_rows_sc_bulletin.jsonl"

csv.field_size_limit(sys.maxsize)

# ─── logging ──────────────────────────────────────────────
log = logging.getLogger("ingest_sc_bulletin")
log.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", "%H:%M:%S")
sh = logging.StreamHandler();              sh.setLevel(logging.INFO);  sh.setFormatter(fmt)
fh = RotatingFileHandler("ingest.log", maxBytes=10_000_000, backupCount=3)
fh.setLevel(logging.DEBUG);               fh.setFormatter(fmt)
log.addHandler(sh); log.addHandler(fh)

# ─── index mapping ────────────────────────────────────────
MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "mapping.total_fields.limit": 1000,
        "highlight.max_analyzed_offset": 10_000_000
    },
    "mappings": {
        "properties": {
            "Date": {
                "type": "date",
                "format": (
                    "yyyy/MM/dd||yyyy/M/d||"
                    "yyyy/MM||yyyy/M||"
                    "yyyy-MM-dd||yyyy-M-d||"
                    "yyyy-MM||yyyy-M||"
                    "strict_date_optional_time"
                )
            },
            "Name": {
                "type": "text",
                "fields": {"raw": {"type": "keyword", "ignore_above": 32766}}
            },
            "html":            { "type": "text" },
            "text_normalized": { "type": "text" }
        }
    }
}

# ─── helpers ──────────────────────────────────────────────
DATE_RX = re.compile(r"""
    ^\s*
    (?P<y>\d{4})        # year
    [/-]
    (?P<m>\d{1,2})      # month
    (?:[/-](?P<d>\d{1,2}))?   # optional day
    \s*$
""", re.X)

def to_iso(date_str: str) -> str | None:
    m = DATE_RX.match(date_str)
    if not m:
        return None
    y, mth = int(m["y"]), int(m["m"])
    day    = int(m["d"] or 1)          # default day=1 if missing
    try:
        return datetime(y, mth, day).strftime("%Y-%m-%d")
    except ValueError:
        return None

def os_client() -> OpenSearch:
    sess = boto3.Session(
        aws_access_key_id     = AWS_ACCESS_KEY_ID,
        aws_secret_access_key = AWS_SECRET_ACCESS_KEY,
        region_name           = REGION,
    )
    auth = AWSV4SignerAuth(sess.get_credentials(), REGION, "es")
    return OpenSearch(
        hosts=[{"host": HOST, "port": 443, "scheme": "https"}],
        http_auth        = auth,
        connection_class = RequestsHttpConnection,
        use_ssl=True, verify_certs=True, http_compress=True,
        timeout=REQ_TIMEOUT
    )

def make_id(row: Dict[str, str]) -> str:
    return hashlib.sha1((row.get("Date","") + row.get("Name","")).encode()).hexdigest()

def csv_stream(path: pathlib.Path, skip: int) -> Iterable[Tuple[int, Dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i <= skip:
                continue
            # normalize or drop Date
            if (d := row.get("Date", "").strip()):
                if iso := to_iso(d):
                    row["Date"] = iso
                else:
                    row.pop("Date", None)
            yield i, {"_index": INDEX, "_id": make_id(row), "_source": row}

def row_count(path: pathlib.Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for _ in f) - 1

# ─── main ────────────────────────────────────────────────
def main() -> None:
    try:
        csv_path = pathlib.Path(CSV_IN)
        if not csv_path.exists():
            log.error("CSV not found: %s", CSV_IN)
            return

        total = row_count(csv_path)
        log.info("Rows in CSV: %s", f"{total:,}")

        os = os_client()
        os.indices.delete(INDEX, ignore=[404]); log.info("Deleted index (if any)")
        os.indices.create(INDEX, body=MAPPING);  log.info("Created index")

        start_row = int(CKPT_FILE.read_text()) if CKPT_FILE.exists() else -1
        ok = fail = 0
        failed: List[dict] = []

        def chunks(it, n):
            it = iter(it)
            while (chunk := list(itertools.islice(it, n))):
                yield chunk

        with tqdm(total=total, initial=start_row+1, unit="doc") as bar:
            for chunk in chunks(csv_stream(csv_path, start_row), BATCH_DOCS):
                ids, actions = zip(*chunk)
                ok_now, errors = helpers.bulk(
                    os, actions,
                    chunk_size=len(actions),
                    max_chunk_bytes=BATCH_BYTES,
                    request_timeout=REQ_TIMEOUT,
                    raise_on_error=False,
                    stats_only=False,
                )
                ok += ok_now
                bar.update(ok_now)

                # retry failures once without Date
                for item in errors:
                    (_, info), = item.items()
                    doc = info.get("data", {}).get("_source", {})
                    doc.pop("Date", None)
                    try:
                        os.index(index=INDEX, id=info["_id"], body=doc,
                                 request_timeout=REQ_TIMEOUT)
                        ok += 1
                    except Exception as e:
                        fail += 1
                        failed.append({"id": info["_id"],
                                       "error": info.get("error", str(e))})

                CKPT_FILE.write_text(str(ids[-1]))
                log.debug("chunk end  ok=%d fail=%d", ok, fail)

        if failed:
            with open(FAIL_FILE, "w", encoding="utf-8") as f:
                json.dump(failed, f, ensure_ascii=False, indent=2)
            log.warning("❗ %d docs still failed – see %s", len(failed), FAIL_FILE)
        else:
            log.info("✅ No permanent failures")

        log.info("Finished  ok=%d  fail=%d", ok, fail)

    except Exception:
        log.error("Fatal error:\n%s", traceback.format_exc())

if __name__ == "__main__":
    main()
