from decimal import Decimal
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from .models import Application, AuditLog, Certificate, Initiative, MessageThread, Notification, Shift, User, VolunteerHour


def log_action(actor, action, entity, details=None):
    AuditLog.objects.create(
        actor=actor if actor and actor.is_authenticated else None,
        action=action,
        entity_type=entity.__class__.__name__ if entity else 'System',
        entity_id=getattr(entity, 'id', None),
        details_json=details or {},
    )


def notify(user, type_, title, body):
    if user:
        Notification.objects.create(user=user, type=type_, title=title, body=body)
        cache.delete(f'header-stats:{user.id}')


def user_can_manage_initiative(user, initiative):
    if not user.is_authenticated:
        return False
    if user.is_platform_admin:
        return True
    if user.is_org_manager and initiative.organization.manager_id == user.id:
        return True
    if user.is_coordinator and initiative.organization.coordinators.filter(id=user.id).exists():
        return True
    return False


def matching_percent(user, initiative):
    if not user.is_authenticated or not user.is_volunteer:
        return 0
    volunteer_skills = set(user.volunteer_skills.values_list('skill_id', flat=True))
    required = set(initiative.required_skills.values_list('id', flat=True))
    if not required:
        return 100
    return int(len(volunteer_skills & required) / len(required) * 100)


def application_allowed(user, initiative, shift=None):
    if not user.is_authenticated or not user.is_volunteer:
        return False, 'Подавати заявки можуть лише волонтери.'
    if not initiative.is_available_for_application:
        return False, 'Ініціатива недоступна для нових заявок.'
    qs = Application.objects.filter(volunteer=user, initiative=initiative).exclude(
        status__in=[Application.Statuses.CANCELLED, Application.Statuses.REJECTED]
    )
    if shift:
        qs = qs.filter(shift=shift)
    if qs.exists():
        return False, 'Ви вже маєте активну заявку на цю ініціативу або зміну.'
    if shift and shift.remaining_spots <= 0:
        return False, 'У цій зміні вже немає вільних місць.'
    if not shift and initiative.remaining_spots <= 0:
        return False, 'В ініціативі вже немає вільних місць.'
    return True, ''


def refresh_counts(application):
    application.initiative.refresh_approved_count()
    if application.shift:
        application.shift.refresh_approved_count()


def issue_certificate_for_hours(hour, issuer):
    existing = Certificate.objects.filter(volunteer=hour.volunteer, initiative=hour.initiative).first()
    if existing:
        return existing
    number = f'VH-{timezone.now().strftime("%Y%m%d")}-{hour.volunteer_id}-{hour.initiative_id}'
    cert = Certificate.objects.create(
        volunteer=hour.volunteer,
        initiative=hour.initiative,
        organization=hour.initiative.organization,
        approved_hours=hour.hours,
        certificate_number=number,
    )
    notify(hour.volunteer, 'certificate', 'Сертифікат видано', f'Сертифікат за ініціативу «{hour.initiative.title}» готовий до перегляду.')
    log_action(issuer, 'issued_certificate', cert, {'hours': str(hour.hours)})
    return cert


def dashboard_numbers():
    cached = cache.get('dashboard_numbers')
    if cached:
        return cached

    sql = """
        SELECT
            (SELECT COUNT(*) FROM hub_user) AS total_users,
            (SELECT COUNT(*) FROM hub_user WHERE role = %s AND status = %s) AS active_volunteers,
            (SELECT COUNT(*) FROM hub_initiative WHERE status = %s) AS active_initiatives,
            (SELECT COUNT(*) FROM hub_application WHERE status IN (%s, %s)) AS pending_applications,
            COALESCE((SELECT SUM(hours) FROM hub_volunteerhour WHERE status = %s), 0) AS approved_hours,
            (SELECT COUNT(*) FROM hub_certificate) AS certificates,
            (SELECT COUNT(*) FROM hub_initiative WHERE status = %s AND urgency_level IN (%s, %s)) AS urgent
    """
    params = [
        User.Roles.VOLUNTEER,
        User.Statuses.ACTIVE,
        Initiative.Statuses.PUBLISHED,
        Application.Statuses.SUBMITTED,
        Application.Statuses.UNDER_REVIEW,
        VolunteerHour.Statuses.APPROVED,
        Initiative.Statuses.PUBLISHED,
        Initiative.Urgency.HIGH,
        Initiative.Urgency.EMERGENCY,
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()

    numbers = {
        'total_users': row[0],
        'active_volunteers': row[1],
        'active_initiatives': row[2],
        'pending_applications': row[3],
        'approved_hours': row[4] or Decimal('0'),
        'certificates': row[5],
        'urgent': row[6],
    }
    cache.set('dashboard_numbers', numbers, 20)
    return numbers
