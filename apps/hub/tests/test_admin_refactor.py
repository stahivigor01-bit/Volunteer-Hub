from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.hub.forms import CategoryForm, InitiativeForm, OrganizationForm, UserAdminForm
from apps.hub.models import Initiative, InitiativeCategory, Organization


class AdminFormBehaviorTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_user(
            username='admin@example.com',
            email='admin@example.com',
            password='pass12345',
            full_name='Адміністратор',
            role=self.user_model.Roles.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.manager = self.user_model.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='pass12345',
            full_name='Менеджер',
            role=self.user_model.Roles.ORGANIZATION_MANAGER,
        )
        self.category = InitiativeCategory.objects.create(name='Освіта', slug='education')
        self.organization = Organization.objects.create(
            name='Добра команда',
            slug='dobra-komanda',
            description='Опис організації',
            city='Київ',
            contact_email='office@example.com',
            manager=self.manager,
        )

    def test_slug_fields_are_internal_and_generated_by_forms(self):
        self.assertNotIn('slug', OrganizationForm().fields)
        self.assertNotIn('slug', InitiativeForm(user=self.manager).fields)
        self.assertNotIn('slug', CategoryForm().fields)

        form = OrganizationForm(data={
            'name': 'Добра команда',
            'description': 'Інша організація з такою ж назвою в іншому місті.',
            'city': 'Львів',
            'address': '',
            'contact_email': 'office2@example.com',
            'phone': '',
            'website': '',
            'status': Organization.Statuses.ACTIVE,
            'manager': self.manager.id,
            'coordinators': [],
        })

        self.assertTrue(form.is_valid(), form.errors)
        org = form.save()
        self.assertNotEqual(org.slug, self.organization.slug)
        self.assertTrue(org.slug.startswith('dobra-komanda'))

    def test_organization_coordinators_field_uses_ukrainian_group_label(self):
        self.user_model.objects.create_user(
            username='coordinator@example.com',
            email='coordinator@example.com',
            password='pass12345',
            full_name='Ірина Ковальчук',
            role=self.user_model.Roles.COORDINATOR,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('organization_create'))

        self.assertContains(response, 'Координатори')
        self.assertNotContains(response, 'Coordinators')
        self.assertContains(response, 'choice-field')
        self.assertContains(response, 'choice-options')
        self.assertNotContains(response, 'class="choice-list form-control"')

    def test_category_name_is_validated_as_unique_without_exposing_slug(self):
        form = CategoryForm(data={
            'name': 'Освіта',
            'description': 'Повтор назви має відхилятися серверною валідацією.',
            'icon': '✦',
            'color': '#2563eb',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_admin_role_cannot_be_assigned_from_admin_user_form(self):
        form = UserAdminForm()
        role_values = [value for value, _ in form.fields['role'].choices]

        self.assertNotIn(self.user_model.Roles.ADMIN, role_values)

        forged = UserAdminForm(data={
            'full_name': 'Новий Адмін',
            'email': 'new.admin@example.com',
            'phone': '',
            'city': 'Київ',
            'role': self.user_model.Roles.ADMIN,
            'status': self.user_model.Statuses.ACTIVE,
            'bio': '',
        })

        self.assertFalse(forged.is_valid())
        self.assertIn('role', forged.errors)


class AdminUiBehaviorTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_user(
            username='ihor@example.com',
            email='ihor@example.com',
            password='pass12345',
            full_name='Стахів Ігор',
            role=self.user_model.Roles.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.second_admin = self.user_model.objects.create_user(
            username='other.admin@example.com',
            email='other.admin@example.com',
            password='pass12345',
            full_name='Другий адміністратор',
            role=self.user_model.Roles.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.volunteer = self.user_model.objects.create_user(
            username='volunteer@example.com',
            email='volunteer@example.com',
            password='pass12345',
            full_name='Марко Савчук',
            role=self.user_model.Roles.VOLUNTEER,
        )
        self.client.force_login(self.admin)

    def test_admin_navigation_and_headers_are_ukrainian_only(self):
        response = self.client.get(reverse('admin_dashboard'))

        self.assertNotContains(response, 'Admin workspace')
        self.assertNotContains(response, 'Admin mission control')
        self.assertNotContains(response, 'KPI')
        self.assertNotContains(response, 'roles')
        self.assertContains(response, 'Адміністрування')

    def test_admin_account_status_cannot_be_toggled(self):
        response = self.client.post(reverse('admin_user_toggle', args=[self.second_admin.id]))
        self.second_admin.refresh_from_db()

        self.assertRedirects(response, reverse('admin_users'))
        self.assertEqual(self.second_admin.status, self.user_model.Statuses.ACTIVE)

    def test_messages_and_notifications_have_search_filters(self):
        for name in ['message_threads', 'notifications']:
            response = self.client.get(reverse(name))

            self.assertContains(response, 'name="q"')
            self.assertContains(response, 'Пошук')


class SeedIdentityTests(TestCase):
    def test_seed_uses_realistic_unique_emails_and_no_lesia_boiko(self):
        call_command('seed', '--skip-media', stdout=StringIO())
        user_model = get_user_model()

        self.assertTrue(user_model.objects.filter(email='ihor.stakhiv@volunteerhub.org.ua').exists())
        self.assertFalse(user_model.objects.filter(email__contains='volunteer.local').exists())
        self.assertFalse(user_model.objects.filter(full_name='Леся Бойко').exists())
