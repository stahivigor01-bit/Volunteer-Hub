#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input --upload-unhashed-files
python manage.py migrate
python manage.py warm_cloudinary_images --limit 220 --workers 6 || true
