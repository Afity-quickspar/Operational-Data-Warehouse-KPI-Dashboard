"""
============================================================================
 PIPELINE ORCHESTRATOR  (the Airflow-free "daily DAG")
============================================================================
A dependency-aware, retrying, self-timing task runner that executes the full
ELT pipeline in the correct order - the same job an Airflow DAG would schedule
daily, minus the server, scheduler and license.

DAG
---
    generate_source_data
            |
        ingest_raw
            |
       dbt_seed_deps  (no-op placeholder / hook point)
            |
        dbt_run  ----->  dbt_test
            |               |
    dbt_source_freshness    |
            |               |
            +-------+-------+
                    |
              export_bi_extracts
                    |
              publish_run_report

Features
--------
* Topological execution with explicit upstream dependencies.
* Per-task retries with backoff, wall-clock timing, and structured logging.
* Freshness gate: warns/fails per the SLA in pipeline_config.yaml.
* A final run-report table (also written to data/logs/run_report_*.md).
* CLI flags:  --skip-generate  (reuse existing raw files / faster refresh)
              --full           (force regenerate)  [default]
              --no-freshness   (skip the freshness gate)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.append(str(Path(__file__).resolve().parent))
from utils.db import load_config
from utils.logger import get_logger

log = get_logger("orchestrate")

DBT_DIR = Path("dbt/warehouse_dbt")
VENV_DBT = Path(".venv/Scripts/dbt.exe")


# ---------------------------------------------------------------------------
# Task abstraction
# ---------------------------------------------------------------------------
@dataclass
class Task:
    name: str
    fn: Callable[[], None]
    upstream: list[str] = field(default_factory=list)
    retries: int = 1
    retry_backoff_sec: float = 3.0
    # runtime state
    status: str = "pending"          # pending|running|success|failed|skipped
    duration_sec: float = 0.0
    attempts: int = 0
    detail: str = ""


class DAG:
    def __init__(self, name: str):
        self.name = name
        self.tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        self.tasks[task.name] = task

    def _topological_order(self) -> list[str]:
        visited, order = set(), []

        def visit(n: str, stack: set[str]):
            if n in visited:
                return
            if n in stack:
                raise ValueError(f"Cycle detected at task '{n}'")
            stack.add(n)
            for up in self.tasks[n].upstream:
                if up not in self.tasks:
                    raise ValueError(f"Task '{n}' depends on unknown task '{up}'")
                visit(up, stack)
            stack.discard(n)
            visited.add(n)
            order.append(n)

        for name in self.tasks:
            visit(name, set())
        return order

    def run(self) -> bool:
        order = self._topological_order()
        log.info(f"DAG '{self.name}' | {len(order)} tasks | order: {' -> '.join(order)}")
        overall_ok = True

        for name in order:
            task = self.tasks[name]
            # Skip if any upstream failed
            failed_up = [u for u in task.upstream if self.tasks[u].status in ("failed", "skipped")]
            if failed_up:
                task.status = "skipped"
                task.detail = f"upstream failed: {', '.join(failed_up)}"
                log.warning(f"[{name}] SKIPPED ({task.detail})")
                overall_ok = False
                continue

            for attempt in range(1, task.retries + 1):
                task.attempts = attempt
                task.status = "running"
                log.info(f"[{name}] running (attempt {attempt}/{task.retries}) ...")
                t0 = time.perf_counter()
                try:
                    task.fn()
                    task.duration_sec = time.perf_counter() - t0
                    task.status = "success"
                    log.info(f"[{name}] SUCCESS in {task.duration_sec:0.2f}s")
                    break
                except Exception as exc:  # noqa: BLE001
                    task.duration_sec = time.perf_counter() - t0
                    task.detail = str(exc).splitlines()[0][:180]
                    log.error(f"[{name}] FAILED (attempt {attempt}): {task.detail}")
                    if attempt < task.retries:
                        time.sleep(task.retry_backoff_sec)
                    else:
                        task.status = "failed"
                        overall_ok = False

        self._publish_report()
        return overall_ok

    def _publish_report(self) -> None:
        try:
            from tabulate import tabulate
        except ImportError:
            tabulate = None

        rows = [
            [t.name, t.status.upper(), f"{t.duration_sec:0.2f}s", t.attempts, t.detail[:60]]
            for t in self.tasks.values()
        ]
        headers = ["Task", "Status", "Duration", "Attempts", "Detail"]
        total = sum(t.duration_sec for t in self.tasks.values())
        n_ok = sum(t.status == "success" for t in self.tasks.values())

        log.info("=" * 78)
        log.info(f"RUN REPORT | {n_ok}/{len(self.tasks)} tasks succeeded | wall={total:0.2f}s")
        if tabulate:
            for line in tabulate(rows, headers=headers, tablefmt="github").splitlines():
                log.info(line)
        else:
            for r in rows:
                log.info("  " + " | ".join(str(x) for x in r))
        log.info("=" * 78)

        # Persist a markdown report artefact
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = Path("data/logs") / f"run_report_{stamp}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        md = [f"# Pipeline run report — {self.name}",
              f"_Generated {datetime.now(timezone.utc).isoformat()} UTC_", "",
              f"**{n_ok}/{len(self.tasks)} tasks succeeded** · wall-clock **{total:0.2f}s**", ""]
        if tabulate:
            md.append(tabulate(rows, headers=headers, tablefmt="github"))
        out.write_text("\n".join(md), encoding="utf-8")
        log.info(f"Run report written to {out}")


# ---------------------------------------------------------------------------
# Task implementations
# ---------------------------------------------------------------------------
def _run_dbt(*args: str) -> None:
    """Invoke dbt inside the project dir with the local profile."""
    cmd = [str(VENV_DBT.resolve()), *args, "--profiles-dir", "."]
    log.info(f"    $ dbt {' '.join(args)}")
    proc = subprocess.run(
        cmd, cwd=str(DBT_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    # Surface a compact tail of dbt output
    tail = [ln for ln in (proc.stdout or "").splitlines()
            if any(k in ln for k in ("PASS", "ERROR", "WARN", "Done.", "Completed", "FAIL", "Failure"))]
    for ln in tail[-12:]:
        log.info("    " + ln.strip())
    if proc.returncode != 0:
        raise RuntimeError(f"dbt {args[0]} exited {proc.returncode}: {tail[-1] if tail else 'see logs'}")


def task_generate() -> None:
    import generate_data
    generate_data.generate()


def task_ingest() -> None:
    import ingest
    ingest.ingest()


def task_dbt_run() -> None:
    _run_dbt("run")


def task_dbt_test() -> None:
    _run_dbt("test")


def task_dbt_freshness() -> None:
    _run_dbt("source", "freshness")


def task_export() -> None:
    import export_bi
    export_bi.export_all()


def task_report() -> None:
    # Lightweight post-run KPI snapshot to prove the marts are queryable.
    import duckdb
    from utils.db import warehouse_path
    con = duckdb.connect(str(warehouse_path()), read_only=True)
    rev = con.execute("select sum(recognized_revenue) from main_marts.kpi_monthly").fetchone()[0]
    seg = con.execute("""select round(max(priority_customer_share)*100,1),
                                round(max(priority_revenue_share)*100,1)
                         from main_marts.customer_segments""").fetchone()
    con.close()
    log.info(f"    KPI snapshot | all-time recognized revenue ${rev:,.0f}")
    log.info(f"    KPI snapshot | priority segment = {seg[0]}% of customers -> {seg[1]}% of revenue")


# ---------------------------------------------------------------------------
# DAG assembly + entrypoint
# ---------------------------------------------------------------------------
def build_dag(skip_generate: bool, run_freshness: bool) -> DAG:
    dag = DAG("operational_warehouse_daily")

    if not skip_generate:
        dag.add(Task("generate_source_data", task_generate, retries=2))
        ingest_up = ["generate_source_data"]
    else:
        ingest_up = []

    dag.add(Task("ingest_raw", task_ingest, upstream=ingest_up, retries=2))
    dag.add(Task("dbt_run", task_dbt_run, upstream=["ingest_raw"], retries=1))
    dag.add(Task("dbt_test", task_dbt_test, upstream=["dbt_run"], retries=1))

    export_up = ["dbt_test"]
    if run_freshness:
        dag.add(Task("dbt_source_freshness", task_dbt_freshness,
                     upstream=["dbt_run"], retries=1))
        export_up.append("dbt_source_freshness")

    dag.add(Task("export_bi_extracts", task_export, upstream=export_up, retries=2))
    dag.add(Task("publish_run_report", task_report, upstream=["export_bi_extracts"]))
    return dag


def main() -> int:
    parser = argparse.ArgumentParser(description="Operational Data Warehouse daily pipeline")
    parser.add_argument("--skip-generate", action="store_true",
                        help="Reuse existing raw files (faster refresh)")
    parser.add_argument("--no-freshness", action="store_true",
                        help="Skip the dbt source-freshness gate")
    args = parser.parse_args()

    cfg = load_config()
    log.info("#" * 78)
    log.info(f"# {cfg['project']['name']}")
    log.info(f"# environment={cfg['project']['environment']} | "
             f"run_started={datetime.now(timezone.utc).isoformat()}")
    log.info("#" * 78)

    dag = build_dag(skip_generate=args.skip_generate, run_freshness=not args.no_freshness)
    ok = dag.run()
    if ok:
        log.info("Pipeline completed successfully. Warehouse is refreshed and tested.")
        return 0
    log.error("Pipeline completed with failures. See run report above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
