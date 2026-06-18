from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.hub.forms import InitiativeForm, OrganizationForm, RegisterForm
from apps.hub.models import Initiative, InitiativeCategory, Organization


class FormRenderingTests(TestCase):
    def test_forms_do_not_render_browser_required_attributes(self):
        html = RegisterForm().as_p()

        self.assertNotIn(' required', html)

    def test_invalid_form_renders_summary_list_and_marks_field(self):
        response = self.client.post('/register/', {
            'full_name': '',
            'email': 'not-an-email',
            'password1': '123',
            'password2': '456',
        })

        self.assertContains(response, 'form-error-list')
        self.assertContains(response, 'has-error')
        self.assertContains(response, 'Перевірте форму')

    def test_custom_photo_preview_script_is_available(self):
        script = (settings.BASE_DIR / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')

        self.assertIn('photo-upload-widget', script)
        self.assertIn('createObjectURL', script)


class ManagedFileFormTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='pass12345',
            full_name='Manager',
            role=user_model.Roles.ORGANIZATION_MANAGER,
        )
        self.organization = Organization.objects.create(
            name='Org',
            slug='org',
            description='Description',
            city='Kyiv',
            contact_email='org@example.com',
            manager=self.manager,
        )
        self.category = InitiativeCategory.objects.create(
            name='Category',
            slug='category',
        )
        self.initiative = Initiative.objects.create(
            organization=self.organization,
            category=self.category,
            title='Old title',
            slug='old-title',
            short_description='Short description',
            description='Long description',
            image='initiatives/old-photo.jpg',
            city='Kyiv',
            start_date='2026-07-01',
            end_date='2026-07-02',
            required_volunteers_count=3,
            created_by=self.manager,
        )

    def test_initiative_form_can_delete_existing_cloudinary_image(self):
        form = InitiativeForm(data={
            'organization': self.organization.id,
            'category': self.category.id,
            'title': 'Old title',
            'slug': 'old-title',
            'short_description': 'Short description',
            'description': 'Long description',
            'urgency_level': Initiative.Urgency.MEDIUM,
            'format': Initiative.Formats.OFFLINE,
            'city': 'Kyiv',
            'location_address': '',
            'start_date': '2026-07-01',
            'end_date': '2026-07-02',
            'required_volunteers_count': 3,
            'beginner_friendly': 'on',
            'accessibility_notes': '',
            'safety_notes': '',
            'contact_person': '',
            'expected_impact': '',
            'status': Initiative.Statuses.PUBLISHED,
            'remove_image': 'on',
        }, instance=self.initiative, user=self.manager)

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        instance.created_by = self.manager
        with patch.object(self.initiative.image.storage, 'delete') as delete:
            instance.save()
            form.save_m2m()
            form.cleanup_replaced_files(instance)

        self.assertEqual(instance.image.name, '')
        delete.assert_called_once_with('initiatives/old-photo.jpg')

    def test_image_field_exposes_custom_photo_preview_metadata(self):
        form = InitiativeForm(instance=self.initiative, user=self.manager)

        attrs = form.fields['image'].widget.attrs

        self.assertEqual(attrs.get('data-photo-upload'), '1')
        self.assertIn('photo-upload-input', attrs.get('class', ''))
        self.assertTrue(attrs.get('data-current-url', '').endswith('/media/initiatives/old-photo.jpg'))

    def test_photo_field_does_not_render_django_default_clear_ui(self):
        self.organization.logo = 'organizations/current-logo.jpg'
        form = OrganizationForm(instance=self.organization)
        html = form.as_p()

        self.assertNotIn('logo-clear', html)
        self.assertNotIn('Наразі:', html)
        self.assertNotIn('Очистити', html)
        self.assertNotIn('Змінити:', html)
        self.assertIn('remove_logo', html)
