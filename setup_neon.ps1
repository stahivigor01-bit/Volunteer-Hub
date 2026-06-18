$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Не знайдено .venv\Scripts\python.exe. Спочатку виконай: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    throw "Не знайдено .env. Створи його з .env.example і встав DATABASE_URL для Neon."
}

Set-Location $ProjectRoot

Write-Host "Applying Django migrations to configured database..." -ForegroundColor Cyan
& $Python manage.py migrate --noinput

Write-Host "Seeding database data..." -ForegroundColor Cyan
& $Python manage.py seed

Write-Host "Neon database is ready." -ForegroundColor Green
