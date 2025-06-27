#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normal_uploader.py – bulk-ingest the *normalized* CSVs
──────────────────────────────────────────────────────
For each CSV below it:

1. **Deletes** any existing index with the same name
2. Re-creates the index with the correct mapping
3. Streams every row in

    data_norm.csv                         →  norm_legal_cases
    Existent_laws_acts_text_norm.csv      →  norm_ext_acts
    existent_laws_other_norm.csv          →  norm_ext_oth
    existent_laws_rules_and_regulations_norm.csv → norm_ext_rul_reg
    cons_panel_norm.csv                   →  cons_panel
"""
from __future__ import annotations
import csv, sys, pathlib, hashlib, re
from datetime import datetime
from typing import Dict, Iterable, Tuple

from tqdm import tqdm
from opensearchpy import OpenSearch, helpers, RequestsHttpConnection, AWSV4SignerAuth
import boto3

# ───────────────────────────  CONFIG  ────────────────────────────
HOST   = "search-stirsat-vhuxip6bjql4c2iahjpkfqjc6i.eu-north-1.es.amazonaws.com"
REGION = "eu-north-1"

add the aws    = ""
add the aws= ""

CHUNK_DOCS   = 100
CHUNK_BYTES  = 8 * 1024 * 1024
REQ_TIMEOUT  = 120
csv.field_size_limit(sys.maxsize)

TARGETS: Tuple[Tuple[str, str], ...] = (
    ("data_norm.csv",                         "norm_legal_cases"),
    ("Existent_laws_acts_text_norm.csv",      "norm_ext_acts"),
    ("existent_laws_other_norm.csv",          "norm_ext_oth"),
    ("existent_laws_rules_and_regulations_norm.csv","norm_ext_rul_reg"),
    ("cons_panel_norm.csv",                   "cons_panel"),          # ← added
)

# ───────────────────────────  MAPPINGS  ───────────────────────────
MAPPING_LEGAL = {
    "settings": { "number_of_shards": 1,
                  "mapping.total_fields.limit": 2000,
                  "highlight.max_analyzed_offset": 10_000_000 },
    "mappings": {
        "properties": {
            "link": {"type": "keyword"},
            "Title": {"type": "text","fields":{"raw":{"type":"keyword","ignore_above":32766}}},
            "Decision_Date":{"type":"date",
                "format":"yyyy/MM/dd||yyyy/M/d||yyyy-MM-dd||yyyy-M-d||strict_date_optional_time"},
            "Panel": {"type": "text"},
            "Case_Number": {"type": "keyword"},
            "judges": {"type": "text"},
            "Mudda_Eng": {"type": "text"},
            "names": {"type": "text"},
            "text": {"type": "text"},
            "response": {"type": "text"},
            "text_normalized": {"type": "text"}
        }
    }
}

MAPPING_EXT = {
    "settings": {
        "number_of_shards": 1,
        "analysis": {
            "analyzer": {
                "html_nepali": {
                    "type": "custom",
                    "char_filter": ["html_strip"],
                    "tokenizer": "icu_tokenizer",
                    "filter": ["lowercase", "icu_folding"]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "file_name": {"type":"text","fields":{"keyword":{"type":"keyword"}}},
            "relative_path": {"type":"keyword"},
            "html": {"type":"text","analyzer":"html_nepali"},
            "text_normalized":{"type":"text"}
        }
    }
}

# ───────────────────────  CLIENT (SigV4)  ────────────────────────
def os_client_sigv4() -> OpenSearch:
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

CLIENT = os_client_sigv4()

# ───────────────────────────  HELPERS  ───────────────────────────
DATE_RX = re.compile(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$")
def to_iso(d: str) -> str | None:
    m = DATE_RX.match(d)
    if not m: return None
    y, mth, day = map(int, m.groups())
    try: return datetime(y, mth, day).strftime("%Y-%m-%d")
    except ValueError: return None

def make_legal_id(r: Dict[str, str]) -> str:
    return hashlib.sha1((r.get("link","")+r.get("Case_Number","")).encode()).hexdigest()

def make_ext_id(r: Dict[str, str]) -> str:
    return r.get("relative_path") or hashlib.sha1(r.get("html","").encode()).hexdigest()

def row_count(path: pathlib.Path) -> int:
    with path.open(encoding="utf-8", newline="") as f:
        return sum(1 for _ in f) - 1

# ──────────────────────────  INGEST  ────────────────────────────
def ingest_file(csv_path: pathlib.Path, index: str) -> None:
    mapping = MAPPING_LEGAL if index == "norm_legal_cases" else MAPPING_EXT

    # delete & recreate index
    if CLIENT.indices.exists(index):
        print(f"🗑️  Deleting old index {index}")
        CLIENT.indices.delete(index)
    CLIENT.indices.create(index, body=mapping)
    print(f"🆕  Created index {index}")

    stream = stream_legal(csv_path, index) if index == "norm_legal_cases" else stream_ext(csv_path, index)
    total = row_count(csv_path)
    ok_docs = fails = 0

    print(f"\n⚡  Ingesting {csv_path.name} → {index}  ({total:,} docs)")
    with tqdm(total=total, unit="doc") as bar:
        for ok, _ in helpers.streaming_bulk(
            CLIENT, stream,
            chunk_size      = CHUNK_DOCS,
            max_chunk_bytes = CHUNK_BYTES,
            request_timeout = REQ_TIMEOUT,
            raise_on_error  = False,
        ):
            if ok: ok_docs += 1
            else:  fails   += 1
            bar.update(1)

    print(f"🎉  {index}: indexed {ok_docs}/{total} docs; failed {fails}")

# ─────────────────────────  STREAMERS  ──────────────────────────
def stream_legal(csv_path: pathlib.Path, index: str) -> Iterable[Dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (d := row.get("Decision_Date", "").strip()):
                iso = to_iso(d)
                if iso:
                    row["Decision_Date"] = iso
                else:
                    row.pop("Decision_Date", None)        # ← drop invalid date
            yield {"_index": index, "_id": make_legal_id(row), "_source": row, "op_type": "index"}

def stream_ext(csv_path: pathlib.Path, index: str) -> Iterable[Dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row = {k.strip("\ufeff "): v for k, v in row.items()}
            yield {"_index": index, "_id": make_ext_id(row), "_source": row, "op_type": "index"}

# ────────────────────────  ENTRY-POINT  ─────────────────────────
def main() -> None:
    for csv_file, idx in TARGETS:
        path = pathlib.Path(csv_file)
        if not path.exists():
            sys.exit(f"❌ CSV not found: {csv_file}")
        ingest_file(path, idx)
    print("\n✅  All normalized indexes created!")

if __name__ == "__main__":
    main()