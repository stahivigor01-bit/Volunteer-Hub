from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings


class DatabaseConfigurationTests(SimpleTestCase):
    def test_database_backend_is_postgresql_only(self):
        self.assertEqual(settings.DATABASES['default']['ENGINE'], 'django.db.backends.postgresql')


class LayoutAndAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username='admin@example.com',
            email='admin@example.com',
            password='admin123',
            full_name='Admin',
            role=user_model.Roles.ADMIN,
        )

    def test_footer_is_removed_from_public_layout(self):
        response = self.client.get('/')

        self.assertNotContains(response, 'site-footer')

    def test_admin_dashboard_uses_workspace_redesign(self):
        self.client.force_login(self.admin)

        response = self.client.get('/admin-panel/')

        self.assertContains(response, 'admin-workspace')
        self.assertContains(response, 'admin-nav')

    def test_custom_select_script_is_available(self):
        text = (settings.BASE_DIR / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')

        self.assertIn('custom-select', text)
        self.assertIn('syncNativeSelect', text)


class NeonWakeMiddlewareTests(SimpleTestCase):
    @override_settings(
        NEON_WAKE_ENABLED=True,
        NEON_API_KEY='token',
        NEON_PROJECT_ID='project-id',
        NEON_ENDPOINT_ID='ep-test',
    )
    def test_operational_error_starts_neon_endpoint_and_returns_503(self):
        from config.middleware import NeonWakeMiddleware

        request = RequestFactory().get('/')
        middleware = NeonWakeMiddleware(lambda request: None)

        with patch('config.middleware.connections') as connections, patch('config.middleware.requests.post') as post:
            connections.__getitem__.return_value.ensure_connection.side_effect = OperationalError('sleeping')
            post.return_value = Mock(status_code=200)

            response = middleware(request)

        self.assertEqual(response.status_code, 503)
        self.assertIn('База даних прокидається', response.content.decode('utf-8'))
        post.assert_called_once()

    @override_settings(
        NEON_WAKE_ENABLED=True,
        NEON_API_KEY='',
        NEON_PROJECT_ID='project-id',
        NEON_ENDPOINT_ID='ep-test',
    )
    def test_missing_neon_configuration_is_explicit(self):
        from config.middleware import validate_neon_settings

        with self.assertRaises(ImproperlyConfigured):
            validate_neon_settings()
