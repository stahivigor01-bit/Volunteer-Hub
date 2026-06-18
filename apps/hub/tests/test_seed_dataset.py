from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.hub.models import (
    Application, Certificate, Initiative, InitiativeCategory, MessageThread,
    Notification, Organization, Shift, Skill, VolunteerHour,
)


class SeedDatasetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed', '--skip-media', stdout=StringIO())

    def test_seed_rebuilds_database_with_expected_people_and_volume(self):
        user_model = get_user_model()

        admin = user_model.objects.get(email='ihor.stakhiv@volunteerhub.org.ua')

        self.assertEqual(admin.full_name, 'Стахів Ігор')
        self.assertEqual(admin.role, user_model.Roles.ADMIN)
        self.assertTrue(admin.has_usable_password())
        self.assertEqual(user_model.objects.count(), 63)
        self.assertEqual(user_model.objects.filter(role=user_model.Roles.ORGANIZATION_MANAGER).count(), 6)
        self.assertEqual(user_model.objects.filter(role=user_model.Roles.COORDINATOR).count(), 8)
        self.assertEqual(user_model.objects.filter(role=user_model.Roles.VOLUNTEER).count(), 48)
        self.assertEqual(Organization.objects.count(), 18)
        self.assertEqual(InitiativeCategory.objects.count(), 18)
        self.assertEqual(Skill.objects.count(), 42)
        self.assertEqual(Initiative.objects.count(), 180)
        self.assertEqual(Shift.objects.count(), 540)
        self.assertEqual(Application.objects.count(), 768)
        self.assertEqual(VolunteerHour.objects.count(), 768)
        self.assertEqual(Certificate.objects.count(), 624)
        self.assertEqual(MessageThread.objects.count(), 768)
        self.assertEqual(Notification.objects.count(), 1110)

    def test_each_seeded_volunteer_has_paginated_personal_data(self):
        user_model = get_user_model()
        volunteer = user_model.objects.get(email='marko.savchuk@gmail.com')

        self.assertTrue(volunteer.has_usable_password())
        self.assertGreater(volunteer.applications.count(), 12)
        self.assertGreater(volunteer.hours.count(), 12)
        self.assertGreater(volunteer.certificates.count(), 12)
        self.assertGreater(volunteer.volunteer_threads.count(), 12)
        self.assertGreater(volunteer.notifications.count(), 12)

    def test_seeded_pages_show_pagination_for_public_and_role_workspaces(self):
        user_model = get_user_model()

        for url in ['/initiatives/', '/organizations/']:
            response = self.client.get(url)
            self.assertContains(response, 'Сторінка 1 з')

        organization = Organization.objects.order_by('slug').first()
        response = self.client.get(f'/organizations/{organization.slug}/')
        self.assertContains(response, 'Сторінка 1 з')

        volunteer = user_model.objects.get(email='marko.savchuk@gmail.com')
        self.client.force_login(volunteer)
        for url in ['/volunteer/applications/', '/volunteer/hours/', '/volunteer/certificates/', '/messages/', '/notifications/']:
            response = self.client.get(url)
            self.assertContains(response, 'Сторінка 1 з', msg_prefix=url)

        coordinator = user_model.objects.get(email='iryna.kovalchuk@mistoturboty.org.ua')
        self.client.force_login(coordinator)
        for url in ['/coordinator/initiatives/', '/coordinator/applications/', '/coordinator/shifts/', '/coordinator/hours/', '/messages/', '/notifications/']:
            response = self.client.get(url)
            self.assertContains(response, 'Сторінка 1 з', msg_prefix=url)

        admin = user_model.objects.get(email='ihor.stakhiv@volunteerhub.org.ua')
        self.client.force_login(admin)
        for url in ['/admin-panel/users/', '/admin-panel/organizations/', '/admin-panel/categories/', '/admin-panel/skills/', '/messages/', '/notifications/']:
            response = self.client.get(url)
            self.assertContains(response, 'Сторінка 1 з', msg_prefix=url)
