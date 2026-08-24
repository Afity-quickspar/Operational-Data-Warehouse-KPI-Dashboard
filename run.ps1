# ============================================================================
#  Operational Data Warehouse — Windows PowerShell task runner
#  Usage:  .\run.ps1 <task>
#  Tasks:  setup | pipeline | dashboard | transform | test | freshness | export
# ============================================================================
param([Parameter(Position=0)][string]$Task = "help")

$Py = ".venv\Scripts\python.exe"

switch ($Task) {
  "setup" {
    python -m venv .venv
    & $Py -m pip install -r requirements.txt
  }
  "pipeline"  { & $Py src\orchestrate.py }
  "refresh"   { & $Py src\orchestrate.py --skip-generate }
  "generate"  { & $Py src\generate_data.py }
  "ingest"    { & $Py src\ingest.py }
  "transform" { Push-Location dbt\warehouse_dbt; & "..\..\$Py" -m dbt.cli.main run --profiles-dir .; Pop-Location }
  "test"      { Push-Location dbt\warehouse_dbt; & "..\..\.venv\Scripts\dbt.exe" test --profiles-dir .; Pop-Location }
  "freshness" { Push-Location dbt\warehouse_dbt; & "..\..\.venv\Scripts\dbt.exe" source freshness --profiles-dir .; Pop-Location }
  "export"    { & $Py src\export_bi.py }
  "dashboard" { & $Py -m streamlit run streamlit_app\app.py }
  default {
    Write-Host "Operational Data Warehouse - tasks:" -ForegroundColor Cyan
    Write-Host "  .\run.ps1 setup      # create venv + install deps"
    Write-Host "  .\run.ps1 pipeline   # run the full daily DAG"
    Write-Host "  .\run.ps1 refresh    # pipeline, reuse existing raw data"
    Write-Host "  .\run.ps1 dashboard  # launch Streamlit app"
    Write-Host "  .\run.ps1 test       # dbt data tests"
    Write-Host "  .\run.ps1 freshness  # dbt source freshness"
    Write-Host "  .\run.ps1 export     # export marts for Power BI"
  }
}
