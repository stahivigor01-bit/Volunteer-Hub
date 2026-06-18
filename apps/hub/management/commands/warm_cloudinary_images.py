import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from apps.hub.models import Initiative, Organization, User
from apps.hub.templatetags.hub_extras import image_avatar, image_card, image_hero, image_logo


class Command(BaseCommand):
    help = 'Warm optimized Cloudinary image transformations used by Volunteer Hub pages.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=220, help='Maximum unique image URLs to warm.')
        parser.add_argument('--workers', type=int, default=6, help='Parallel fetch workers.')

    def handle(self, *args, **options):
        urls = self.collect_urls()[: options['limit']]
        if not urls:
            self.stdout.write(self.style.WARNING('No Cloudinary images found to warm.'))
            return

        started = time.perf_counter()
        success = 0
        failed = 0
        total_bytes = 0

        self.stdout.write(f'Warming {len(urls)} Cloudinary image variants...')
        with ThreadPoolExecutor(max_workers=max(options['workers'], 1)) as executor:
            futures = {executor.submit(self.fetch, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    size, elapsed_ms, content_type = future.result()
                except Exception as exc:
                    failed += 1
                    self.stdout.write(self.style.WARNING(f'  failed: {url} ({exc})'))
                    continue
                success += 1
                total_bytes += size
                self.stdout.write(f'  {size / 1024:.1f} KB · {elapsed_ms:.0f} ms · {content_type}')

        elapsed = time.perf_counter() - started
        self.stdout.write(
            self.style.SUCCESS(
                f'Warmup finished: {success} ok, {failed} failed, {total_bytes / 1024:.1f} KB, {elapsed:.1f}s.'
            )
        )

    def collect_urls(self):
        urls = []

        for url in self.design_asset_urls():
            urls.extend([image_card(url), image_hero(url)])

        for image in Initiative.objects.exclude(image='').values_list('image', flat=True):
            if not image:
                continue
            url = self.absolute_media_url(image)
            urls.extend([image_card(url), image_hero(url)])

        for logo in Organization.objects.exclude(logo='').values_list('logo', flat=True):
            if logo:
                urls.append(image_logo(self.absolute_media_url(logo)))

        for avatar in User.objects.exclude(avatar='').values_list('avatar', flat=True):
            if avatar:
                urls.append(image_avatar(self.absolute_media_url(avatar)))

        unique = []
        seen = set()
        for url in urls:
            if 'res.cloudinary.com' not in url or url in seen:
                continue
            unique.append(url)
            seen.add(url)
        return unique

    def design_asset_urls(self):
        manifest = getattr(settings, 'DESIGN_ASSETS_MANIFEST', None)
        if not manifest or not manifest.exists():
            return []
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return []
        return [value for value in data.values() if value]

    def absolute_media_url(self, value):
        text = str(value)
        if text.startswith(('http://', 'https://')):
            return text
        try:
            return default_storage.url(text)
        except Exception:
            return settings.MEDIA_URL.rstrip('/') + '/' + text.lstrip('/')

    def fetch(self, url):
        request = urllib.request.Request(url, headers={'User-Agent': 'VolunteerHubImageWarmup/1.0'})
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read()
            content_type = response.headers.get('content-type', 'unknown')
        elapsed_ms = (time.perf_counter() - started) * 1000
        return len(payload), elapsed_ms, content_type
