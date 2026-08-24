"""
============================================================================
 BI EXTRACT EXPORTER  (marts -> Power BI / Streamlit consumable files)
============================================================================
Power BI Desktop connects most reliably to flat files or a folder of extracts.
This module materialises the marts as BOTH .csv (universally importable) and
.parquet (typed, compressed, fast) under data/exports/, plus a small
`_manifest.json` describing row counts and freshness for the BI layer.

Run standalone:   python src/export_bi.py
Or via the DAG:   task export_bi_extracts
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from utils.db import connect, load_config
from utils.logger import get_logger

log = get_logger("export")

MARTS_SCHEMA = "main_marts"   # dbt materialises marts under main_marts.*


def export_all() -> dict[str, int]:
    cfg = load_config()
    exports_dir = Path(cfg["exports"]["dir"])
    exports_dir.mkdir(parents=True, exist_ok=True)
    fmt = cfg["exports"]["format"]
    tables = cfg["exports"]["tables"]

    con = connect(read_only=True)
    manifest: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warehouse": cfg["warehouse"]["database_path"],
        "tables": {},
    }
    counts: dict[str, int] = {}

    for tbl in tables:
        fq = f"{MARTS_SCHEMA}.{tbl}"
        n = con.execute(f"SELECT count(*) FROM {fq}").fetchone()[0]
        counts[tbl] = n

        if fmt in ("csv", "both"):
            csv_path = (exports_dir / f"{tbl}.csv").resolve().as_posix()
            con.execute(f"COPY (SELECT * FROM {fq}) TO '{csv_path}' (HEADER, DELIMITER ',');")
        if fmt in ("parquet", "both"):
            pq_path = (exports_dir / f"{tbl}.parquet").resolve().as_posix()
            con.execute(f"COPY (SELECT * FROM {fq}) TO '{pq_path}' (FORMAT PARQUET);")

        manifest["tables"][tbl] = {"rows": n}
        log.info(f"Exported {tbl:<20} rows={n:>8,}  -> {fmt}")

    con.close()
    with open(exports_dir / "_manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    total = sum(counts.values())
    log.info("-" * 56)
    log.info(f"BI export complete | {len(tables)} tables | {total:,} rows | dir={exports_dir.resolve()}")
    return counts


if __name__ == "__main__":
    export_all()
