import json
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.hub.models import Initiative, InitiativeCategory, Organization, VolunteerHour


class CloudinaryCleanupCommandTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.volunteer = user_model.objects.create_user(
            username='volunteer@example.com',
            email='volunteer@example.com',
            password='pass12345',
            full_name='Volunteer',
            role=user_model.Roles.VOLUNTEER,
            avatar='media/avatars/used-avatar',
        )
        self.coordinator = user_model.objects.create_user(
            username='coordinator@example.com',
            email='coordinator@example.com',
            password='pass12345',
            full_name='Coordinator',
            role=user_model.Roles.COORDINATOR,
        )
        self.organization = Organization.objects.create(
            name='Org',
            slug='org',
            description='Description',
            logo='media/organizations/used-logo',
            city='Kyiv',
            contact_email='org@example.com',
        )
        self.category = InitiativeCategory.objects.create(name='Category', slug='category')
        self.initiative = Initiative.objects.create(
            organization=self.organization,
            category=self.category,
            title='Initiative',
            slug='initiative',
            short_description='Short description',
            description='Long description',
            image='media/initiatives/used-image',
            city='Kyiv',
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            required_volunteers_count=2,
            created_by=self.coordinator,
        )
        VolunteerHour.objects.create(
            volunteer=self.volunteer,
            initiative=self.initiative,
            hours='2.50',
            description='Evidence upload',
            evidence_file='media/evidence/used-proof.pdf',
        )

    def test_dry_run_reports_unused_assets_without_deleting(self):
        with self.override_manifest() as manifest:
            with patch('cloudinary.api.resources', side_effect=self.fake_resources), \
                    patch('cloudinary.api.delete_resources') as delete_resources:
                out = StringIO()
                call_command('cleanup_cloudinary_assets', stdout=out)
                self.assertTrue(manifest.exists())

        output = out.getvalue()
        self.assertIn('Dry run', output)
        self.assertIn('media/organizations/unused-logo', output)
        self.assertIn('volunteer_hub/design/unused-design', output)
        self.assertNotIn('media/organizations/used-logo', output)
        self.assertNotIn('media/evidence/young-proof.pdf', output)
        self.assertFalse(delete_resources.called)

    def test_delete_removes_only_unused_old_assets_by_resource_type(self):
        with self.override_manifest():
            with patch('cloudinary.api.resources', side_effect=self.fake_resources), \
                    patch('cloudinary.api.delete_resources') as delete_resources:
                out = StringIO()
                call_command('cleanup_cloudinary_assets', '--delete', '--min-age-hours', '1', stdout=out)

        image_calls = [
            call.kwargs for call in delete_resources.call_args_list
            if call.kwargs.get('resource_type') == 'image'
        ]
        raw_calls = [
            call.kwargs for call in delete_resources.call_args_list
            if call.kwargs.get('resource_type') == 'raw'
        ]
        deleted_ids = [item for call in delete_resources.call_args_list for item in call.args[0]]

        self.assertTrue(image_calls)
        self.assertTrue(raw_calls)
        self.assertIn('media/organizations/unused-logo', deleted_ids)
        self.assertIn('volunteer_hub/design/unused-design', deleted_ids)
        self.assertIn('media/evidence/old-proof.pdf', deleted_ids)
        self.assertNotIn('media/organizations/used-logo', deleted_ids)
        self.assertNotIn('media/evidence/young-proof.pdf', deleted_ids)

    def override_manifest(self):
        temp_dir = tempfile.TemporaryDirectory()
        manifest = Path(temp_dir.name) / 'cloudinary-assets.json'
        manifest.write_text(
            json.dumps({
                'hero_volunteers': 'https://res.cloudinary.com/demo/image/upload/v123/volunteer_hub/design/used-design.jpg',
            }),
            encoding='utf-8',
        )
        override = override_settings(
            DESIGN_ASSETS_MANIFEST=manifest,
            CLOUDINARY_STORAGE={'CLOUD_NAME': 'demo', 'API_KEY': 'key', 'API_SECRET': 'secret', 'SECURE': True},
        )
        override.enable()

        class Context:
            def __enter__(self_inner):
                return manifest

            def __exit__(self_inner, exc_type, exc, tb):
                override.disable()
                temp_dir.cleanup()

        return Context()

    def fake_resources(self, **options):
        prefix = options['prefix']
        resource_type = options.get('resource_type', 'image')
        old = (timezone.now() - timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
        young = (timezone.now() - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
        data = {
            ('image', 'media/avatars'): [
                {'public_id': 'media/avatars/used-avatar', 'created_at': old},
            ],
            ('image', 'media/organizations'): [
                {'public_id': 'media/organizations/used-logo', 'created_at': old},
                {'public_id': 'media/organizations/unused-logo', 'created_at': old},
            ],
            ('image', 'media/initiatives'): [
                {'public_id': 'media/initiatives/used-image', 'created_at': old},
            ],
            ('image', 'media/seed'): [],
            ('image', 'volunteer_hub/design'): [
                {'public_id': 'volunteer_hub/design/used-design', 'created_at': old},
                {'public_id': 'volunteer_hub/design/unused-design', 'created_at': old},
            ],
            ('raw', 'media/evidence'): [
                {'public_id': 'media/evidence/used-proof.pdf', 'created_at': old},
                {'public_id': 'media/evidence/old-proof.pdf', 'created_at': old},
                {'public_id': 'media/evidence/young-proof.pdf', 'created_at': young},
            ],
        }
        return {'resources': data.get((resource_type, prefix), [])}
