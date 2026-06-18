import json
import re
from collections import defaultdict
from datetime import timedelta, timezone as datetime_timezone
from pathlib import Path
from urllib.parse import urlparse

import cloudinary
import cloudinary.api
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.hub.models import Initiative, Organization, User, VolunteerHour


class Command(BaseCommand):
    help = 'Delete unused Cloudinary assets that belong to this project.'

    IMAGE_PREFIXES = (
        'media/avatars',
        'media/organizations',
        'media/initiatives',
        'media/seed',
        'volunteer_hub/design',
    )
    RAW_PREFIXES = (
        'media/evidence',
    )

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true', help='Actually delete unused assets. Default is dry-run.')
        parser.add_argument('--min-age-hours', type=float, default=1, help='Never delete assets newer than this age.')
        parser.add_argument('--max-results', type=int, default=500, help='Cloudinary page size per API request.')
        parser.add_argument('--batch-size', type=int, default=100, help='Delete batch size.')

    def handle(self, *args, **options):
        self.configure_cloudinary()
        used = self.collect_used_public_ids()
        unused_by_type = self.collect_unused_assets(used, options['min_age_hours'], options['max_results'])
        total_unused = sum(len(items) for items in unused_by_type.values())

        action = 'Deleting' if options['delete'] else 'Dry run'
        self.stdout.write(
            f'{action}: {total_unused} unused Cloudinary assets '
            f'({len(used["image"])} used images, {len(used["raw"])} used raw files).'
        )
        for resource_type, assets in unused_by_type.items():
            if not assets:
                continue
            self.stdout.write(f'{resource_type}:')
            for asset in assets[:30]:
                self.stdout.write(f'  {asset["public_id"]}')
            if len(assets) > 30:
                self.stdout.write(f'  ...and {len(assets) - 30} more')

        if not options['delete'] or total_unused == 0:
            return

        deleted = 0
        for resource_type, assets in unused_by_type.items():
            public_ids = [asset['public_id'] for asset in assets]
            for batch in self.chunks(public_ids, options['batch_size']):
                cloudinary.api.delete_resources(batch, resource_type=resource_type, type='upload', invalidate=True)
                deleted += len(batch)
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} unused Cloudinary assets.'))

    def configure_cloudinary(self):
        config = settings.CLOUDINARY_STORAGE
        missing = [key for key in ('CLOUD_NAME', 'API_KEY', 'API_SECRET') if not config.get(key)]
        if missing:
            raise CommandError('Cloudinary ENV is incomplete: ' + ', '.join(missing))
        cloudinary.config(
            cloud_name=config['CLOUD_NAME'],
            api_key=config['API_KEY'],
            api_secret=config['API_SECRET'],
            secure=True,
        )

    def collect_used_public_ids(self):
        used = {'image': set(), 'raw': set()}
        for value in User.objects.exclude(avatar='').values_list('avatar', flat=True):
            self.add_public_id(used, 'image', value)
        for value in Organization.objects.exclude(logo='').values_list('logo', flat=True):
            self.add_public_id(used, 'image', value)
        for value in Initiative.objects.exclude(image='').values_list('image', flat=True):
            self.add_public_id(used, 'image', value)
        for value in VolunteerHour.objects.exclude(evidence_file='').values_list('evidence_file', flat=True):
            self.add_public_id(used, 'raw', value, keep_extension=True)
        for value in self.design_asset_urls():
            self.add_public_id(used, 'image', value)
        return used

    def design_asset_urls(self):
        manifest = getattr(settings, 'DESIGN_ASSETS_MANIFEST', None)
        if not manifest or not Path(manifest).exists():
            return []
        try:
            data = json.loads(Path(manifest).read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return []
        return [value for value in data.values() if value]

    def add_public_id(self, used, resource_type, value, keep_extension=False):
        public_id = self.normalize_public_id(value, keep_extension=keep_extension)
        if public_id:
            used[resource_type].add(public_id)

    def normalize_public_id(self, value, keep_extension=False):
        if not value:
            return ''
        text = str(value).strip()
        if text.startswith(('http://', 'https://')):
            text = self.public_id_from_url(text)
        text = text.strip('/')
        if not keep_extension:
            text = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', text)
        return text

    def public_id_from_url(self, url):
        path = urlparse(url).path
        marker = '/upload/'
        if marker not in path:
            return ''
        rest = path.split(marker, 1)[1].strip('/')
        parts = rest.split('/')
        version_index = next((index for index, part in enumerate(parts) if re.fullmatch(r'v\d+', part)), None)
        if version_index is not None:
            parts = parts[version_index + 1:]
        return '/'.join(parts)

    def collect_unused_assets(self, used, min_age_hours, max_results):
        unused = defaultdict(list)
        for resource_type, prefixes in [('image', self.IMAGE_PREFIXES), ('raw', self.RAW_PREFIXES)]:
            for prefix in prefixes:
                for asset in self.iter_resources(resource_type, prefix, max_results):
                    public_id = asset.get('public_id', '')
                    if not public_id or public_id in used[resource_type]:
                        continue
                    if self.is_too_young(asset.get('created_at'), min_age_hours):
                        continue
                    unused[resource_type].append(asset)
        return unused

    def iter_resources(self, resource_type, prefix, max_results):
        next_cursor = None
        while True:
            response = cloudinary.api.resources(
                resource_type=resource_type,
                type='upload',
                prefix=prefix,
                max_results=max_results,
                next_cursor=next_cursor,
            )
            for resource in response.get('resources', []):
                yield resource
            next_cursor = response.get('next_cursor')
            if not next_cursor:
                break

    def is_too_young(self, created_at, min_age_hours):
        if min_age_hours <= 0:
            return False
        parsed = parse_datetime(created_at) if created_at else None
        if parsed is None:
            return True
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone=datetime_timezone.utc)
        return timezone.now() - parsed < timedelta(hours=min_age_hours)

    def chunks(self, values, size):
        for index in range(0, len(values), size):
            yield values[index:index + size]
