# One command local bootup on Windows: API on :8000, UI on :5173.   powershell -File cicd\scripts\dev.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")

if (-not (Test-Path "$root\server\.venv")) {
  python -m venv "$root\server\.venv"
  & "$root\server\.venv\Scripts\pip" install -q -r "$root\server\requirements.txt"
}
if (-not (Test-Path "$root\client\node_modules")) { Push-Location "$root\client"; npm install --no-audit --no-fund; Pop-Location }
if (-not (Test-Path "$root\migrated\carddemo-batch\target\carddemo-batch-0.1.0.jar")) {
  mvn -B -q -DskipTests -f "$root\migrated\carddemo-batch\pom.xml" package
}

$api = Start-Process -PassThru -WorkingDirectory "$root\server" -FilePath "$root\server\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn app.main:app --reload --port 8000"
$ui = Start-Process -PassThru -WorkingDirectory "$root\client" -FilePath "npm.cmd" -ArgumentList "run dev"
Write-Host "API http://localhost:8000/docs   UI http://localhost:5173   (Ctrl+C to stop)"
try { Wait-Process -Id $api.Id, $ui.Id } finally { Stop-Process -Id $api.Id, $ui.Id -Force -ErrorAction SilentlyContinue }
