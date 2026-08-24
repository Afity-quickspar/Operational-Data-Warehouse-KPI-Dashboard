# ============================================================================
#  Operational Data Warehouse — task runner
#  Usage:  make <target>     (on Windows, use `make` via Git Bash, or run the
#          equivalent commands from run.ps1)
# ============================================================================
PY := .venv/Scripts/python.exe
DBT := ../../.venv/Scripts/dbt.exe

.PHONY: help setup generate ingest transform test freshness export pipeline dashboard docs clean

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:           ## Create venv and install dependencies
	python -m venv .venv && $(PY) -m pip install -r requirements.txt

generate:        ## Generate synthetic source data
	$(PY) src/generate_data.py

ingest:          ## Stage raw CSV/JSON into DuckDB
	$(PY) src/ingest.py

transform:       ## Run dbt models
	cd dbt/warehouse_dbt && $(DBT) run --profiles-dir .

test:            ## Run dbt data tests
	cd dbt/warehouse_dbt && $(DBT) test --profiles-dir .

freshness:       ## Run dbt source freshness checks
	cd dbt/warehouse_dbt && $(DBT) source freshness --profiles-dir .

export:          ## Export marts to CSV + Parquet for Power BI
	$(PY) src/export_bi.py

pipeline:        ## Run the full daily DAG end-to-end
	$(PY) src/orchestrate.py

dashboard:       ## Launch the Streamlit self-serve app
	$(PY) -m streamlit run streamlit_app/app.py

docs:            ## Build & serve dbt docs
	cd dbt/warehouse_dbt && $(DBT) docs generate --profiles-dir . && $(DBT) docs serve --profiles-dir .

clean:           ## Remove generated data/warehouse artefacts
	rm -f data/warehouse/*.duckdb data/raw/*.csv data/raw/*.json data/exports/*.csv data/exports/*.parquet
