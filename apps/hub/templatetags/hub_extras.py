from django import template

register = template.Library()

ROLE_LABELS = {
    'volunteer': 'Волонтер',
    'coordinator': 'Координатор',
    'organization_manager': 'Менеджер організації',
    'admin': 'Адміністратор',
}
STATUS_LABELS = {
    'active': 'Активний', 'inactive': 'Неактивний',
    'pending': 'Очікує перевірки', 'published': 'Опублікована', 'draft': 'Чернетка',
    'paused': 'Призупинена', 'completed': 'Завершена', 'cancelled': 'Скасована', 'archived': 'Архівована',
    'submitted': 'Подана', 'under_review': 'На розгляді', 'approved': 'Підтверджена', 'rejected': 'Відхилена',
    'attended': 'Участь підтверджена', 'missed': 'Не з’явився', 'issued': 'Видано', 'revoked': 'Анульовано',
    'open': 'Відкрите', 'closed': 'Закрите', 'resolved': 'Вирішене',
    'waiting_for_volunteer': 'Очікує волонтера', 'waiting_for_coordinator': 'Очікує координатора',
}
URGENCY_LABELS = {'low': 'Низька', 'medium': 'Середня', 'high': 'Висока', 'emergency': 'Термінова'}
FORMAT_LABELS = {'offline': 'Офлайн', 'online': 'Онлайн', 'hybrid': 'Гібридна'}
NOTIFICATION_TYPE_LABELS = {
    'admin_digest': 'Адмін-дайджест',
    'manager_digest': 'Дайджест менеджера',
    'coordinator_queue': 'Черга координатора',
    'volunteer_activity': 'Оновлення участі',
    'system': 'Системне сповіщення',
    'application': 'Заявка',
    'hours': 'Волонтерські години',
    'certificate': 'Сертифікат',
    'message': 'Повідомлення',
}

@register.filter
def role_label(value):
    return ROLE_LABELS.get(value, value)

@register.filter
def status_label(value):
    return STATUS_LABELS.get(value, value)

@register.filter
def urgency_label(value):
    return URGENCY_LABELS.get(value, value)

@register.filter
def format_label(value):
    return FORMAT_LABELS.get(value, value)

@register.filter
def notification_type_label(value):
    return NOTIFICATION_TYPE_LABELS.get(value, str(value).replace('_', ' ').capitalize())

@register.filter
def urgency_class(value):
    return {
        'low': 'badge badge-calm',
        'medium': 'badge badge-sky',
        'high': 'badge badge-orange',
        'emergency': 'badge badge-danger',
    }.get(value, 'badge')

@register.filter
def status_class(value):
    return {
        'approved': 'badge badge-success',
        'attended': 'badge badge-success',
        'published': 'badge badge-success',
        'submitted': 'badge badge-sky',
        'under_review': 'badge badge-orange',
        'rejected': 'badge badge-danger',
        'cancelled': 'badge badge-muted',
        'archived': 'badge badge-muted',
        'completed': 'badge badge-success',
        'emergency': 'badge badge-danger',
    }.get(value, 'badge badge-muted')

@register.filter
def percent(value, total):
    try:
        total = float(total)
        if total == 0:
            return 0
        return min(int(float(value) / total * 100), 100)
    except Exception:
        return 0
