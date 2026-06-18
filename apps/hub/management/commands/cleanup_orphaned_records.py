from django.core.management.base import BaseCommand
from django.db import transaction

from apps.hub.models import (
    Application,
    AuditLog,
    Certificate,
    Initiative,
    Message,
    MessageThread,
    Notification,
    Organization,
    Shift,
    User,
    VolunteerHour,
)


class Command(BaseCommand):
    help = 'Delete stale records left after initiative/application cleanup.'

    DEMO_NOTIFICATION_TYPES = (
        'admin_digest',
        'manager_digest',
        'coordinator_queue',
        'volunteer_activity',
    )

    AUDIT_ENTITY_MODELS = {
        'Application': Application,
        'Certificate': Certificate,
        'Initiative': Initiative,
        'MessageThread': MessageThread,
        'Notification': Notification,
        'Organization': Organization,
        'Shift': Shift,
        'User': User,
        'VolunteerHour': VolunteerHour,
    }

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show counts without deleting records.')
        parser.add_argument(
            '--keep-demo-notifications',
            action='store_true',
            help='Do not delete old generated seed notification batches.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        orphan_threads = MessageThread.objects.filter(initiative__isnull=True, application__isnull=True)
        orphan_thread_count = orphan_threads.count()
        orphan_message_count = Message.objects.filter(thread__in=orphan_threads).count()

        audit_count = self.orphan_audit_logs().count()
        demo_notifications = self.demo_notifications()
        demo_notification_count = 0 if options['keep_demo_notifications'] else demo_notifications.count()

        if dry_run:
            self.stdout.write(
                f'Dry run: {orphan_thread_count} orphan message threads, '
                f'{orphan_message_count} messages, {audit_count} orphan audit logs, '
                f'{demo_notification_count} stale demo notifications.'
            )
            return

        orphan_threads.delete()
        self.orphan_audit_logs().delete()
        if not options['keep_demo_notifications']:
            demo_notifications.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {orphan_thread_count} orphan message threads, '
                f'{orphan_message_count} messages, {audit_count} orphan audit logs, '
                f'{demo_notification_count} stale demo notifications.'
            )
        )

    def orphan_audit_logs(self):
        querysets = []
        for entity_type, model in self.AUDIT_ENTITY_MODELS.items():
            querysets.append(
                AuditLog.objects.filter(entity_type=entity_type, entity_id__isnull=False)
                .exclude(entity_id__in=model.objects.values('id'))
            )
        if not querysets:
            return AuditLog.objects.none()
        combined = querysets[0]
        for queryset in querysets[1:]:
            combined = combined | queryset
        return combined.distinct()

    def demo_notifications(self):
        return Notification.objects.filter(
            type__in=self.DEMO_NOTIFICATION_TYPES,
            initiative__isnull=True,
            application__isnull=True,
            volunteer_hour__isnull=True,
            message_thread__isnull=True,
            certificate__isnull=True,
        )
