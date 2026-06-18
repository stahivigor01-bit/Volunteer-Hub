import re
import time
import urllib.request

from django.core.management.base import BaseCommand
from django.test import Client


IMAGE_URL_PATTERNS = (
    re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE),
    re.compile(r"url\('([^']+)'\)", re.IGNORECASE),
    re.compile(r'url\("([^"]+)"\)', re.IGNORECASE),
)


class Command(BaseCommand):
    help = 'Measure rendered page image URLs and optional Cloudinary transfer timings.'

    def add_arguments(self, parser):
        parser.add_argument(
            'paths',
            nargs='*',
            default=['/', '/initiatives/', '/organizations/'],
            help='Local paths to render, for example /initiatives/.',
        )
        parser.add_argument('--fetch', action='store_true', help='Download image files and measure transfer time.')
        parser.add_argument('--limit', type=int, default=8, help='Maximum images to download per page with --fetch.')

    def handle(self, *args, **options):
        client = Client()
        for path in options['paths']:
            started = time.perf_counter()
            response = client.get(path)
            render_ms = (time.perf_counter() - started) * 1000
            html = response.content.decode('utf-8', errors='ignore')
            urls = self.extract_image_urls(html)
            cloudinary_urls = [url for url in urls if 'res.cloudinary.com' in url]
            optimized_urls = [url for url in cloudinary_urls if '/image/upload/f_auto,q_auto' in url]
            raw_urls = [url for url in cloudinary_urls if '/image/upload/f_auto,q_auto' not in url]

            self.stdout.write(
                f'{path} status={response.status_code} render_ms={render_ms:.1f} '
                f'images={len(urls)} cloudinary={len(cloudinary_urls)} '
                f'optimized={len(optimized_urls)} raw={len(raw_urls)}'
            )
            if raw_urls:
                for url in raw_urls[:3]:
                    self.stdout.write(self.style.WARNING(f'  raw: {url}'))
            if options['fetch']:
                self.fetch_images(optimized_urls[:options['limit']])

    def extract_image_urls(self, html):
        urls = []
        for pattern in IMAGE_URL_PATTERNS:
            urls.extend(pattern.findall(html))
        cleaned = []
        seen = set()
        for url in urls:
            if url.startswith(('data:', 'blob:', '#')):
                continue
            if url not in seen:
                cleaned.append(url)
                seen.add(url)
        return cleaned

    def fetch_images(self, urls):
        for url in urls:
            request = urllib.request.Request(url, headers={'User-Agent': 'VolunteerHubImageMeasure/1.0'})
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = response.read()
                    content_type = response.headers.get('content-type', 'unknown')
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'  fetch failed: {url} ({exc})'))
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.stdout.write(f'  {len(payload) / 1024:.1f} KB · {elapsed_ms:.0f} ms · {content_type} · {url}')
