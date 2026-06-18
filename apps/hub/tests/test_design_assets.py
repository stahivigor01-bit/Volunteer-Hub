from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class DesignAssetTests(SimpleTestCase):
    def test_templates_css_and_seed_do_not_reference_svg_assets(self):
        checked_roots = [
            settings.BASE_DIR / 'templates',
            settings.BASE_DIR / 'static' / 'css',
            settings.BASE_DIR / 'apps' / 'hub' / 'management' / 'commands',
        ]
        vector_suffix = ''.join(['.', 's', 'v', 'g'])
        vector_tag = ''.join(['<', 's', 'v', 'g'])
        offenders = []
        for root in checked_roots:
            for path in root.rglob('*'):
                if path.is_file() and path.suffix in {'.html', '.css', '.py'}:
                    text = path.read_text(encoding='utf-8')
                    if vector_suffix in text or vector_tag in text.lower():
                        offenders.append(path.relative_to(settings.BASE_DIR).as_posix())

        self.assertEqual(offenders, [])

    def test_required_photo_assets_are_local_raster_files(self):
        photo_dir = settings.BASE_DIR / 'static' / 'images' / 'photos'
        required = {
            'hero-volunteers.jpg',
            'aid-packing.jpg',
            'community-care.jpg',
            'outdoor-aid.jpg',
            'donation-work.jpg',
            'default-initiative.jpg',
        }

        self.assertTrue(photo_dir.exists())
        missing = sorted(name for name in required if not (photo_dir / name).exists())
        self.assertEqual(missing, [])

        for name in required:
            path = photo_dir / name
            self.assertGreater(path.stat().st_size, 50_000, name)
