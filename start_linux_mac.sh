#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.example to .env and set Neon DATABASE_URL."
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

python -c "import django, cloudinary, dj_database_url, psycopg" >/dev/null 2>&1 || pip install -r requirements.txt

if [ "${1:-}" = "--setup" ]; then
  python manage.py migrate --noinput
  python manage.py seed
else
  echo "Skipping database setup. Use ./start_linux_mac.sh --setup after schema or seed changes."
fi

python scripts/open_when_ready.py "http://127.0.0.1:8000/healthz/" "http://127.0.0.1:8000/" &
python manage.py runserver
