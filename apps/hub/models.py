from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.files.storage import FileSystemStorage
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from cloudinary_storage.storage import RawMediaCloudinaryStorage


def evidence_file_storage():
    default_backend = settings.STORAGES.get('default', {}).get('BACKEND', '')
    if default_backend == 'cloudinary_storage.storage.MediaCloudinaryStorage':
        return RawMediaCloudinaryStorage()
    return FileSystemStorage()


class User(AbstractUser):
    class Roles(models.TextChoices):
        VOLUNTEER = 'volunteer', 'Волонтер'
        COORDINATOR = 'coordinator', 'Координатор'
        ORGANIZATION_MANAGER = 'organization_manager', 'Менеджер організації'
        ADMIN = 'admin', 'Адміністратор'

    class Statuses(models.TextChoices):
        ACTIVE = 'active', 'Активний'
        INACTIVE = 'inactive', 'Неактивний'

    email = models.EmailField('Email', unique=True)
    full_name = models.CharField('ПІБ', max_length=160)
    phone = models.CharField('Телефон', max_length=32, blank=True)
    role = models.CharField('Роль', max_length=32, choices=Roles.choices, default=Roles.VOLUNTEER)
    status = models.CharField('Статус', max_length=16, choices=Statuses.choices, default=Statuses.ACTIVE)
    avatar = models.ImageField('Аватар', upload_to='avatars/', blank=True)
    city = models.CharField('Місто', max_length=100, blank=True)
    bio = models.TextField('Про себе', blank=True)
    last_login_at = models.DateTimeField('Останній вхід', null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'full_name']

    def __str__(self):
        return self.full_name or self.email

    @property
    def is_volunteer(self):
        return self.role == self.Roles.VOLUNTEER

    @property
    def is_coordinator(self):
        return self.role == self.Roles.COORDINATOR

    @property
    def is_org_manager(self):
        return self.role == self.Roles.ORGANIZATION_MANAGER

    @property
    def is_platform_admin(self):
        return self.role == self.Roles.ADMIN or self.is_superuser


class Organization(models.Model):
    class Statuses(models.TextChoices):
        PENDING = 'pending', 'Очікує перевірки'
        ACTIVE = 'active', 'Активна'
        SUSPENDED = 'suspended', 'Призупинена'

    name = models.CharField('Назва', max_length=180)
    slug = models.SlugField('Slug', unique=True, max_length=200)
    description = models.TextField('Опис')
    logo = models.ImageField('Логотип', upload_to='organizations/', blank=True)
    city = models.CharField('Місто', max_length=100)
    address = models.CharField('Адреса', max_length=220, blank=True)
    contact_email = models.EmailField('Контактний email')
    phone = models.CharField('Телефон', max_length=32, blank=True)
    website = models.URLField('Сайт', blank=True)
    status = models.CharField('Статус', max_length=16, choices=Statuses.choices, default=Statuses.ACTIVE)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_organizations')
    coordinators = models.ManyToManyField(User, blank=True, related_name='coordinated_organizations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class InitiativeCategory(models.Model):
    name = models.CharField('Назва', max_length=120)
    slug = models.SlugField('Slug', unique=True, max_length=140)
    description = models.TextField('Опис', blank=True)
    icon = models.CharField('Іконка', max_length=32, default='✦')
    color = models.CharField('Колір', max_length=32, default='#f97316')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField('Назва', max_length=120, unique=True)
    category = models.CharField('Категорія', max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Initiative(models.Model):
    class Urgency(models.TextChoices):
        LOW = 'low', 'Низька'
        MEDIUM = 'medium', 'Середня'
        HIGH = 'high', 'Висока'
        EMERGENCY = 'emergency', 'Термінова'

    class Formats(models.TextChoices):
        OFFLINE = 'offline', 'Офлайн'
        ONLINE = 'online', 'Онлайн'
        HYBRID = 'hybrid', 'Гібридна'

    class Statuses(models.TextChoices):
        DRAFT = 'draft', 'Чернетка'
        PUBLISHED = 'published', 'Опублікована'
        PAUSED = 'paused', 'Призупинена'
        COMPLETED = 'completed', 'Завершена'
        CANCELLED = 'cancelled', 'Скасована'
        ARCHIVED = 'archived', 'Архівована'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='initiatives')
    category = models.ForeignKey(InitiativeCategory, on_delete=models.PROTECT, related_name='initiatives')
    title = models.CharField('Назва', max_length=180)
    slug = models.SlugField('Slug', unique=True, max_length=220)
    short_description = models.CharField('Короткий опис', max_length=280)
    description = models.TextField('Опис')
    image = models.ImageField('Зображення', upload_to='initiatives/', blank=True)
    urgency_level = models.CharField('Терміновість', max_length=16, choices=Urgency.choices, default=Urgency.MEDIUM)
    format = models.CharField('Формат', max_length=16, choices=Formats.choices, default=Formats.OFFLINE)
    city = models.CharField('Місто/регіон', max_length=100)
    location_address = models.CharField('Локація', max_length=220, blank=True)
    start_date = models.DateField('Дата початку')
    end_date = models.DateField('Дата завершення')
    required_volunteers_count = models.PositiveIntegerField('Потрібно волонтерів', default=1)
    approved_volunteers_count = models.PositiveIntegerField('Затверджено волонтерів', default=0)
    required_skills = models.ManyToManyField(Skill, blank=True, related_name='initiatives')
    beginner_friendly = models.BooleanField('Підходить новачкам', default=True)
    accessibility_notes = models.TextField('Доступність', blank=True)
    safety_notes = models.TextField('Безпекові нотатки', blank=True)
    contact_person = models.CharField('Контактна особа', max_length=140, blank=True)
    expected_impact = models.CharField('Очікуваний вплив', max_length=220, blank=True)
    status = models.CharField('Статус', max_length=16, choices=Statuses.choices, default=Statuses.PUBLISHED)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_initiatives')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['organization', 'status', '-created_at']),
            models.Index(fields=['city', 'status']),
        ]

    def __str__(self):
        return self.title

    @property
    def remaining_spots(self):
        return max(self.required_volunteers_count - self.approved_volunteers_count, 0)

    @property
    def is_full(self):
        return self.remaining_spots <= 0

    @property
    def is_available_for_application(self):
        return self.status == self.Statuses.PUBLISHED and not self.is_full

    def refresh_approved_count(self):
        count = self.applications.filter(status__in=['approved', 'attended']).count()
        self.approved_volunteers_count = count
        self.save(update_fields=['approved_volunteers_count'])


class VolunteerSkill(models.Model):
    volunteer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='volunteer_skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('volunteer', 'skill')]


class VolunteerAvailability(models.Model):
    volunteer = models.OneToOneField(User, on_delete=models.CASCADE, related_name='availability')
    weekdays = models.BooleanField('Будні', default=True)
    weekends = models.BooleanField('Вихідні', default=True)
    mornings = models.BooleanField('Ранок', default=False)
    afternoons = models.BooleanField('День', default=True)
    evenings = models.BooleanField('Вечір', default=False)
    remote_only = models.BooleanField('Тільки дистанційно', default=False)
    preferred_city = models.CharField('Бажане місто/регіон', max_length=100, blank=True)


class Shift(models.Model):
    class Statuses(models.TextChoices):
        OPEN = 'open', 'Відкрита'
        FULL = 'full', 'Заповнена'
        CLOSED = 'closed', 'Закрита'
        CANCELLED = 'cancelled', 'Скасована'

    initiative = models.ForeignKey(Initiative, on_delete=models.CASCADE, related_name='shifts')
    title = models.CharField('Назва зміни', max_length=160)
    shift_date = models.DateField('Дата')
    start_time = models.TimeField('Початок')
    end_time = models.TimeField('Завершення')
    location = models.CharField('Місце', max_length=220, blank=True)
    max_volunteers = models.PositiveIntegerField('Максимум волонтерів', default=5)
    approved_count = models.PositiveIntegerField('Затверджено', default=0)
    status = models.CharField('Статус', max_length=16, choices=Statuses.choices, default=Statuses.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['shift_date', 'start_time']
        indexes = [
            models.Index(fields=['initiative', 'status', 'shift_date']),
            models.Index(fields=['status', 'shift_date', 'start_time']),
        ]

    def __str__(self):
        return f'{self.title} — {self.shift_date}'

    @property
    def remaining_spots(self):
        return max(self.max_volunteers - self.approved_count, 0)

    @property
    def duration_hours(self):
        start = self.start_time.hour + self.start_time.minute / 60
        end = self.end_time.hour + self.end_time.minute / 60
        return max(round(end - start, 2), 0)

    def refresh_approved_count(self):
        count = self.applications.filter(status__in=['approved', 'attended']).count()
        self.approved_count = count
        self.status = self.Statuses.FULL if count >= self.max_volunteers else self.Statuses.OPEN
        self.save(update_fields=['approved_count', 'status'])


class Application(models.Model):
    class Statuses(models.TextChoices):
        SUBMITTED = 'submitted', 'Подана'
        UNDER_REVIEW = 'under_review', 'На розгляді'
        APPROVED = 'approved', 'Підтверджена'
        REJECTED = 'rejected', 'Відхилена'
        CANCELLED = 'cancelled', 'Скасована'
        ATTENDED = 'attended', 'Участь підтверджена'
        MISSED = 'missed', 'Не з’явився'

    volunteer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    initiative = models.ForeignKey(Initiative, on_delete=models.CASCADE, related_name='applications')
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name='applications')
    status = models.CharField('Статус', max_length=24, choices=Statuses.choices, default=Statuses.SUBMITTED)
    motivation_text = models.TextField('Мотивація', max_length=1000)
    coordinator_comment = models.TextField('Коментар координатора', blank=True)
    rejection_reason = models.TextField('Причина відхилення', blank=True)
    cancel_reason = models.TextField('Причина скасування', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['initiative', 'status', '-created_at']),
            models.Index(fields=['volunteer', 'status', '-created_at']),
            models.Index(fields=['shift', 'status']),
        ]

    def __str__(self):
        return f'{self.volunteer} → {self.initiative}'


class VolunteerHour(models.Model):
    class Statuses(models.TextChoices):
        DRAFT = 'draft', 'Чернетка'
        SUBMITTED = 'submitted', 'Подано'
        APPROVED = 'approved', 'Підтверджено'
        REJECTED = 'rejected', 'Відхилено'

    volunteer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hours')
    initiative = models.ForeignKey(Initiative, on_delete=models.CASCADE, related_name='hours')
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    hours = models.DecimalField('Години', max_digits=5, decimal_places=2, validators=[MinValueValidator(0.25)])
    description = models.TextField('Опис виконаної роботи', max_length=1200)
    evidence_file = models.FileField('Підтвердження', upload_to='evidence/', blank=True, storage=evidence_file_storage)
    status = models.CharField('Статус', max_length=16, choices=Statuses.choices, default=Statuses.SUBMITTED)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_hours')
    review_comment = models.TextField('Коментар', blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['initiative', 'status', '-submitted_at']),
            models.Index(fields=['volunteer', 'status', '-submitted_at']),
            models.Index(fields=['shift', 'status']),
        ]


class Certificate(models.Model):
    class Statuses(models.TextChoices):
        ISSUED = 'issued', 'Видано'
        REVOKED = 'revoked', 'Анульовано'

    volunteer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    initiative = models.ForeignKey(Initiative, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    approved_hours = models.DecimalField('Підтверджені години', max_digits=6, decimal_places=2)
    certificate_number = models.CharField('Номер сертифіката', max_length=64, unique=True)
    issue_date = models.DateField('Дата видачі', default=timezone.localdate)
    status = models.CharField('Статус', max_length=16, choices=Statuses.choices, default=Statuses.ISSUED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date']


class MessageThread(models.Model):
    class Statuses(models.TextChoices):
        OPEN = 'open', 'Відкрите'
        WAITING_FOR_VOLUNTEER = 'waiting_for_volunteer', 'Очікує волонтера'
        WAITING_FOR_COORDINATOR = 'waiting_for_coordinator', 'Очікує координатора'
        RESOLVED = 'resolved', 'Вирішене'
        CLOSED = 'closed', 'Закрите'

    volunteer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='volunteer_threads')
    coordinator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='coordinator_threads')
    initiative = models.ForeignKey(Initiative, on_delete=models.SET_NULL, null=True, blank=True)
    application = models.ForeignKey(Application, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField('Тема', max_length=180)
    status = models.CharField('Статус', max_length=32, choices=Statuses.choices, default=Statuses.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['volunteer', '-updated_at']),
            models.Index(fields=['coordinator', '-updated_at']),
            models.Index(fields=['status', '-updated_at']),
        ]

    def __str__(self):
        return self.subject


class Message(models.Model):
    thread = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message_text = models.TextField('Повідомлення', max_length=2000)
    is_read = models.BooleanField('Прочитано', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['thread', 'is_read', 'created_at']),
            models.Index(fields=['is_read', 'sender']),
        ]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField('Тип', max_length=60)
    title = models.CharField('Заголовок', max_length=180)
    body = models.TextField('Текст')
    is_read = models.BooleanField('Прочитано', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['user', 'type', '-created_at']),
        ]


class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField('Дія', max_length=140)
    entity_type = models.CharField('Сутність', max_length=80)
    entity_id = models.PositiveIntegerField('ID сутності', null=True, blank=True)
    details_json = models.JSONField('Деталі', default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
