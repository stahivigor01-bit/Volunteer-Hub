from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import FileSystemStorage

from apps.hub.models import Initiative, Organization, User, VolunteerHour


MEDIA_FIELDS = (
    (User, 'avatar'),
    (Organization, 'logo'),
    (Initiative, 'image'),
    (VolunteerHour, 'evidence_file'),
)


class Command(BaseCommand):
    help = 'Move existing local model uploads from MEDIA_ROOT to the configured Cloudinary storage.'

    def add_arguments(self, parser):
        parser.add_argument('--delete-local', action='store_true', help='Delete local files after successful upload.')

    def handle(self, *args, **options):
        if isinstance(default_storage, FileSystemStorage):
            raise CommandError('Default storage is still local. Set Cloudinary ENV before running this command.')

        moved = 0
        skipped = 0
        for model, field_name in MEDIA_FIELDS:
            for obj in model.objects.exclude(**{field_name: ''}):
                field_file = getattr(obj, field_name)
                original_name = field_file.name
                if not original_name or original_name.startswith('http'):
                    skipped += 1
                    continue

                local_path = settings.MEDIA_ROOT / original_name
                if not local_path.exists():
                    skipped += 1
                    continue

                upload_name = Path(original_name).name
                with local_path.open('rb') as handle:
                    field_file.save(upload_name, File(handle), save=False)
                obj.save(update_fields=[field_name])
                moved += 1
                self.stdout.write(self.style.SUCCESS(f'{model.__name__}.{field_name}: {original_name} -> {field_file.name}'))

                if options['delete_local']:
                    local_path.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f'Moved {moved} file(s), skipped {skipped}.'))
