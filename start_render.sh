#!/usr/bin/env bash
set -o errexit

if [ "${CLOUDINARY_CLEANUP_ON_START:-1}" = "1" ]; then
  python manage.py cleanup_cloudinary_assets --delete --min-age-hours "${CLOUDINARY_CLEANUP_MIN_AGE_HOURS:-1}" || true
fi

exec gunicorn config.wsgi:application
