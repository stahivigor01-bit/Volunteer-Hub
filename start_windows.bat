@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

if not exist .env (
  echo Missing .env. Copy .env.example to .env and set Neon DATABASE_URL.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  py -m venv .venv
  if errorlevel 1 goto fail
)

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Missing %PYTHON%.
  pause
  exit /b 1
)

"%PYTHON%" -c "import django, cloudinary, dj_database_url, psycopg" > nul 2> nul
if errorlevel 1 (
  echo Installing Python dependencies...
  "%PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)

if /I "%~1"=="--setup" (
  echo Applying Neon database migrations...
  "%PYTHON%" manage.py migrate --noinput
  if errorlevel 1 goto fail

  echo Seeding Neon database...
  "%PYTHON%" manage.py seed
  if errorlevel 1 goto fail

  echo Warming Cloudinary image cache...
  "%PYTHON%" manage.py warm_cloudinary_images --limit 220 --workers 6
  if errorlevel 1 echo Image cache warmup skipped. The site can still start.
) else (
  echo Skipping database setup. Use start_windows.bat --setup after schema or seed changes.
)

set "HOST=127.0.0.1"
set "PORT=8000"
set "PREFERRED_PORT=8000"

:find_port
netstat -ano -p tcp | findstr /R /C:":%PORT% .*LISTENING" > nul
if %ERRORLEVEL% EQU 0 (
  set /a PORT+=1
  if %PORT% GTR 8099 (
    echo No free ports found from 8000 to 8099.
    pause
    exit /b 1
  )
  goto find_port
)

set "URL=http://%HOST%:%PORT%/"
set "HEALTH_URL=http://%HOST%:%PORT%/healthz/"
if not "%PORT%"=="%PREFERRED_PORT%" echo Port %PREFERRED_PORT% is busy. Using %PORT% instead.
echo Starting Volunteer Hub at %URL%
start "" /min "%PYTHON%" scripts\open_when_ready.py "%HEALTH_URL%" "%URL%"
"%PYTHON%" manage.py runserver %HOST%:%PORT%
pause
exit /b 0

:fail
echo Startup failed.
pause
exit /b 1
