from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError
from django.http import HttpResponse
from django.utils.cache import patch_cache_control

import requests


def validate_neon_settings():
    missing = [
        name for name in ('NEON_API_KEY', 'NEON_PROJECT_ID', 'NEON_ENDPOINT_ID')
        if not getattr(settings, name, '')
    ]
    if missing:
        raise ImproperlyConfigured('Missing Neon settings: ' + ', '.join(missing))


class NeonWakeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.NEON_WAKE_ENABLED:
            return self.get_response(request)

        try:
            return self.get_response(request)
        except OperationalError:
            validate_neon_settings()
            wake_neon_endpoint()
            return database_waking_response()


def wake_neon_endpoint():
    cache_key = f'neon-wake:{settings.NEON_PROJECT_ID}:{settings.NEON_ENDPOINT_ID}'
    if cache.get(cache_key):
        return
    url = (
        'https://console.neon.tech/api/v2/projects/'
        f'{settings.NEON_PROJECT_ID}/endpoints/{settings.NEON_ENDPOINT_ID}/start'
    )
    requests.post(
        url,
        headers={
            'Authorization': f'Bearer {settings.NEON_API_KEY}',
            'Accept': 'application/json',
        },
        timeout=settings.NEON_WAKE_TIMEOUT,
    )
    cache.set(cache_key, True, 30)


def database_waking_response():
    return HttpResponse(
        '<!doctype html><html lang="uk"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>База даних прокидається</title></head>'
        '<body style="font-family:Arial,sans-serif;margin:0;min-height:100vh;'
        'display:grid;place-items:center;background:#f6f8fb;color:#111827">'
        '<main style="max-width:560px;padding:32px;text-align:center">'
        '<h1>База даних прокидається</h1>'
        '<p>Сайт тимчасово недоступний, поки Neon запускає compute endpoint. '
        'Оновіть сторінку за кілька секунд.</p>'
        '</main></body></html>',
        status=503,
    )


class NoCacheCsrfFormMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        content_type = response.headers.get('Content-Type', '')
        if (
            response.status_code == 200
            and 'text/html' in content_type
            and not getattr(response, 'streaming', False)
            and b'csrfmiddlewaretoken' in response.content
        ):
            patch_cache_control(response, no_cache=True, no_store=True, must_revalidate=True, private=True, max_age=0)
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
