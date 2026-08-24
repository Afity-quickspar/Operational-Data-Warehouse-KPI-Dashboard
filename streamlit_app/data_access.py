"""
Cached data-access layer for the Streamlit app.

Every query hits the DuckDB warehouse read-only and is memoised with
st.cache_data so the UI stays snappy. All marts live under `main_marts`.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st
import yaml

# Resolve project paths relative to this file (streamlit_app/ -> project root)
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse" / "warehouse.duckdb"
CONFIG_PATH = ROOT / "config" / "pipeline_config.yaml"
MARTS = "main_marts"


@st.cache_resource(show_spinner=False)
def _con() -> duckdb.DuckDBPyConnection:
    # A single shared read-only connection for the app session.
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(show_spinner=False)
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@st.cache_data(show_spinner=False)
def q(sql: str) -> pd.DataFrame:
    """Run an arbitrary read-only SQL query and return a DataFrame."""
    return _con().execute(sql).df()


# --- Convenience loaders -----------------------------------------------------
@st.cache_data(show_spinner=False)
def kpi_monthly() -> pd.DataFrame:
    return q(f"SELECT * FROM {MARTS}.kpi_monthly ORDER BY month")


@st.cache_data(show_spinner=False)
def kpi_daily() -> pd.DataFrame:
    return q(f"SELECT * FROM {MARTS}.kpi_daily ORDER BY date_key")


@st.cache_data(show_spinner=False)
def customer_segments() -> pd.DataFrame:
    return q(f"SELECT * FROM {MARTS}.customer_segments")


@st.cache_data(show_spinner=False)
def fct_orders() -> pd.DataFrame:
    return q(f"SELECT * FROM {MARTS}.fct_orders")


@st.cache_data(show_spinner=False)
def fct_subscriptions() -> pd.DataFrame:
    return q(f"SELECT * FROM {MARTS}.fct_subscriptions")


@st.cache_data(show_spinner=False)
def cohort_retention() -> pd.DataFrame:
    return q(f"SELECT * FROM {MARTS}.cohort_retention ORDER BY cohort_month, months_since_signup")


@st.cache_data(show_spinner=False)
def dim_customers() -> pd.DataFrame:
    return q(f"SELECT * FROM {MARTS}.dim_customers")


@st.cache_data(show_spinner=False)
def filter_options() -> dict:
    """Distinct values that drive the global sidebar filters."""
    c = _con()
    return {
        "regions": [r[0] for r in c.execute(
            f"SELECT DISTINCT region FROM {MARTS}.dim_customers ORDER BY 1").fetchall()],
        "plans": [r[0] for r in c.execute(
            f"SELECT DISTINCT plan FROM {MARTS}.dim_customers ORDER BY 1").fetchall()],
        "channels": [r[0] for r in c.execute(
            f"SELECT DISTINCT acquisition_channel FROM {MARTS}.dim_customers ORDER BY 1").fetchall()],
        "tiers": ["High-Value", "Core", "Occasional", "Dormant"],
        "min_date": c.execute(f"SELECT min(order_date) FROM {MARTS}.fct_orders").fetchone()[0],
        "max_date": c.execute(f"SELECT max(order_date) FROM {MARTS}.fct_orders").fetchone()[0],
    }


def warehouse_exists() -> bool:
    return DB_PATH.exists()
