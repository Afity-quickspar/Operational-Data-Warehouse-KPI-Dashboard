"""
DuckDB connection + config helpers.

DuckDB is our warehouse engine — a free, embedded, columnar OLAP database that
speaks ANSI SQL and is a drop-in analytical substitute for Snowflake for
local / small-team workloads. One .duckdb file is the entire warehouse.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import duckdb
import yaml

_CONFIG_PATH = Path("config/pipeline_config.yaml")


@functools.lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Parse and cache the pipeline YAML config."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def warehouse_path() -> Path:
    cfg = load_config()
    p = Path(cfg["warehouse"]["database_path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection to the warehouse file."""
    con = duckdb.connect(str(warehouse_path()), read_only=read_only)
    # Pragmas for reproducible, well-behaved analytical sessions
    con.execute("PRAGMA enable_progress_bar=false;")
    con.execute("SET threads TO 4;")
    return con


def ensure_schemas(con: duckdb.DuckDBPyConnection) -> None:
    """Create the raw/staging/marts schemas if they do not yet exist."""
    cfg = load_config()["warehouse"]
    for schema_key in ("raw_schema", "staging_schema", "marts_schema"):
        con.execute(f'CREATE SCHEMA IF NOT EXISTS {cfg[schema_key]};')
