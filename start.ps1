# Start AP Desk: builds the UI if needed, then serves API + UI on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not (Test-Path "$root\.venv")) {
    python -m venv "$root\.venv"
    & "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt"
}
if (-not (Test-Path "$root\data\samples\manifest.json")) {
    & "$root\.venv\Scripts\python.exe" "$root\scripts\generate_invoices.py"
}
if (-not (Test-Path "$root\frontend\dist\index.html")) {
    Push-Location "$root\frontend"; npm install; npm run build; Pop-Location
}
Push-Location "$root\backend"
Write-Host "AP Desk running at http://127.0.0.1:8000" -ForegroundColor Cyan
& "$root\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
