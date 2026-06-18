import json
from pathlib import Path

import cloudinary
import cloudinary.uploader
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


DESIGN_ASSETS = {
    'hero_volunteers': 'hero-volunteers.jpg',
    'aid_packing': 'aid-packing.jpg',
    'community_care': 'community-care.jpg',
    'outdoor_aid': 'outdoor-aid.jpg',
    'donation_work': 'donation-work.jpg',
    'default_initiative': 'default-initiative.jpg',
}


class Command(BaseCommand):
    help = 'Upload bundled design photos to Cloudinary and write the design asset manifest.'

    def add_arguments(self, parser):
        parser.add_argument('--folder', default='volunteer_hub/design', help='Cloudinary folder for design assets.')

    def handle(self, *args, **options):
        storage_config = settings.CLOUDINARY_STORAGE
        missing = [key for key in ('CLOUD_NAME', 'API_KEY', 'API_SECRET') if not storage_config.get(key)]
        if missing:
            raise CommandError('Cloudinary ENV is incomplete: ' + ', '.join(missing))

        cloudinary.config(
            cloud_name=storage_config['CLOUD_NAME'],
            api_key=storage_config['API_KEY'],
            api_secret=storage_config['API_SECRET'],
            secure=True,
        )

        source_dir = settings.BASE_DIR / 'static' / 'images' / 'photos'
        manifest = {}
        for key, filename in DESIGN_ASSETS.items():
            source = source_dir / filename
            if not source.exists():
                raise CommandError(f'Missing design photo: {source}')

            public_id = Path(filename).stem
            result = cloudinary.uploader.upload(
                str(source),
                folder=options['folder'],
                public_id=public_id,
                overwrite=True,
                invalidate=True,
                resource_type='image',
            )
            manifest[key] = result['secure_url']
            self.stdout.write(self.style.SUCCESS(f'{filename} -> {manifest[key]}'))

        settings.DESIGN_ASSETS_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        settings.DESIGN_ASSETS_MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        self.stdout.write(self.style.SUCCESS(f'Wrote {settings.DESIGN_ASSETS_MANIFEST}'))
