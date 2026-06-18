from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.hub.models import (
    Application,
    AuditLog,
    Initiative,
    InitiativeCategory,
    Message,
    MessageThread,
    Notification,
    Organization,
)


class InitiativeCascadeCleanupTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.volunteer = user_model.objects.create_user(
            username='volunteer@example.com',
            email='volunteer@example.com',
            password='pass12345',
            full_name='Volunteer',
            role=user_model.Roles.VOLUNTEER,
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
            city='Kyiv',
            contact_email='org@example.com',
        )
        self.organization.coordinators.add(self.coordinator)
        self.category = InitiativeCategory.objects.create(name='Category', slug='category')
        self.initiative = Initiative.objects.create(
            organization=self.organization,
            category=self.category,
            title='Initiative',
            slug='initiative',
            short_description='Short description',
            description='Long description',
            city='Kyiv',
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            required_volunteers_count=2,
            created_by=self.coordinator,
        )

    def test_deleting_initiative_deletes_message_thread_messages_and_related_notification(self):
        application = Application.objects.create(
            volunteer=self.volunteer,
            initiative=self.initiative,
            status=Application.Statuses.SUBMITTED,
            motivation_text='I can help with this initiative.',
        )
        thread = MessageThread.objects.create(
            volunteer=self.volunteer,
            coordinator=self.coordinator,
            initiative=self.initiative,
            application=application,
            subject='Application thread',
        )
        Message.objects.create(thread=thread, sender=self.volunteer, message_text='Hello')
        Notification.objects.create(
            user=self.coordinator,
            type='application',
            title='New application',
            body='A volunteer applied.',
            initiative=self.initiative,
            application=application,
            message_thread=thread,
        )

        self.initiative.delete()

        self.assertFalse(MessageThread.objects.exists())
        self.assertFalse(Message.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_cleanup_command_deletes_existing_orphan_threads_and_audit_logs(self):
        thread = MessageThread.objects.create(
            volunteer=self.volunteer,
            coordinator=self.coordinator,
            subject='Old orphan thread',
        )
        Message.objects.create(thread=thread, sender=self.volunteer, message_text='Old message')
        AuditLog.objects.create(
            actor=self.coordinator,
            action='deleted',
            entity_type='Initiative',
            entity_id=self.initiative.id + 999,
            details_json={},
        )

        out = StringIO()
        call_command('cleanup_orphaned_records', stdout=out)

        self.assertFalse(MessageThread.objects.exists())
        self.assertFalse(Message.objects.exists())
        self.assertFalse(AuditLog.objects.exists())
        self.assertIn('orphan message threads', out.getvalue())
