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

"%PYTHON%" -c "import django, cloudinary, dj_database_url, psycopg, waitress" > nul 2> nul
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

if /I "%CLOUDINARY_CLEANUP_ON_START%"=="1" (
  if "%CLOUDINARY_CLEANUP_MIN_AGE_HOURS%"=="" set "CLOUDINARY_CLEANUP_MIN_AGE_HOURS=1"
  echo Cleaning unused Cloudinary assets...
  "%PYTHON%" manage.py cleanup_cloudinary_assets --delete --min-age-hours "%CLOUDINARY_CLEANUP_MIN_AGE_HOURS%"
  if errorlevel 1 echo Cloudinary cleanup skipped. The site can still start.
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

if /I "%~1"=="--dev" goto start_dev

set "DEBUG=0"
echo Building optimized static files...
"%PYTHON%" manage.py collectstatic --noinput
if errorlevel 1 goto fail

set "WAITRESS=.venv\Scripts\waitress-serve.exe"
if not exist "%WAITRESS%" (
  echo Missing %WAITRESS%.
  pause
  exit /b 1
)
if "%WAITRESS_THREADS%"=="" set "WAITRESS_THREADS=6"
echo Starting production server with %WAITRESS_THREADS% worker threads...
"%WAITRESS%" --listen=%HOST%:%PORT% --threads=%WAITRESS_THREADS% config.wsgi:application
pause
exit /b 0

:start_dev
set "DEBUG=1"
echo Starting Django development server...
"%PYTHON%" manage.py runserver %HOST%:%PORT%
pause
exit /b 0

:fail
echo Startup failed.
pause
exit /b 1
