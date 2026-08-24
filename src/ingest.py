"""
============================================================================
 STAGED INGESTION  (raw -> DuckDB `raw` schema)
============================================================================
Loads the mixed-format source files (CSV + semi-structured JSON) into the
warehouse `raw` schema using DuckDB's native readers. This is the "EL" of
ELT: land the data faithfully, defer transformation to dbt.

* CSV     -> read_csv_auto (schema inference, typed columns)
* JSON    -> read_json_auto + JSON path extraction for nested `properties`
* Adds an `_ingested_at` audit column to every table (freshness anchor).
* Idempotent: each table is CREATE OR REPLACE'd on every run.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from utils.db import connect, ensure_schemas, load_config
from utils.logger import get_logger

log = get_logger("ingest")


def ingest() -> dict[str, int]:
    cfg = load_config()
    raw_dir = Path(cfg["ingestion"]["raw_dir"]).resolve()
    raw_schema = cfg["warehouse"]["raw_schema"]

    con = connect()
    ensure_schemas(con)
    counts: dict[str, int] = {}

    def _p(name: str) -> str:
        # DuckDB accepts forward slashes on Windows; normalise for SQL literal.
        return str(raw_dir / name).replace("\\", "/")

    # ---- CSV sources --------------------------------------------------------
    csv_sources = {
        "customers": "customers.csv",
        "orders": "orders.csv",
        "subscriptions": "subscriptions.csv",
        "web_sessions": "web_sessions.csv",
        "marketing_spend": "marketing_spend.csv",
    }
    for table, fname in csv_sources.items():
        path = _p(fname)
        con.execute(f"""
            CREATE OR REPLACE TABLE {raw_schema}.{table} AS
            SELECT *, now() AS _ingested_at
            FROM read_csv_auto('{path}', header=true, sample_size=-1);
        """)
        n = con.execute(f"SELECT count(*) FROM {raw_schema}.{table}").fetchone()[0]
        counts[table] = n
        log.info(f"Staged raw.{table:<16} <- {fname:<22} rows={n:>10,}")

    # ---- JSON source (nested properties flattened) --------------------------
    events_path = _p("events.json")
    con.execute(f"""
        CREATE OR REPLACE TABLE {raw_schema}.events AS
        SELECT
            event_id,
            customer_id,
            event_type,
            CAST(event_ts AS TIMESTAMP)              AS event_ts,
            json_extract_string(properties, '$.platform')        AS platform,
            json_extract_string(properties, '$.app_version')     AS app_version,
            CAST(json_extract(properties, '$.session_len_sec') AS BIGINT) AS session_len_sec,
            json_extract_string(properties, '$.feature')         AS feature,
            now() AS _ingested_at
        FROM read_json_auto('{events_path}');
    """)
    n = con.execute(f"SELECT count(*) FROM {raw_schema}.events").fetchone()[0]
    counts["events"] = n
    log.info(f"Staged raw.{'events':<16} <- {'events.json':<22} rows={n:>10,}")

    total = sum(counts.values())
    log.info("-" * 60)
    log.info(f"Ingestion complete | tables={len(counts)} | total rows={total:,}")

    # ---- lightweight landing-zone sanity checks -----------------------------
    min_orders = cfg["quality"]["min_rows_orders"]
    if counts.get("orders", 0) < min_orders:
        log.warning(f"orders row count {counts['orders']:,} below SLA floor {min_orders:,}")

    con.close()
    return counts


if __name__ == "__main__":
    ingest()
