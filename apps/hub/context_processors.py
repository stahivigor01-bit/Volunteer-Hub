import json

from django.conf import settings
from django.templatetags.static import static


def header_stats(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'unread_notifications_count': 0, 'unread_messages_count': 0}
    unread_notifications = user.notifications.filter(is_read=False).count()
    unread_messages = 0
    if hasattr(user, 'volunteer_threads'):
        unread_messages += sum(t.messages.filter(is_read=False).exclude(sender=user).count() for t in user.volunteer_threads.all())
    if hasattr(user, 'coordinator_threads'):
        unread_messages += sum(t.messages.filter(is_read=False).exclude(sender=user).count() for t in user.coordinator_threads.all())
    return {'unread_notifications_count': unread_notifications, 'unread_messages_count': unread_messages}


def design_assets(request):
    fallbacks = {
        'hero_volunteers': static('images/photos/hero-volunteers.jpg'),
        'aid_packing': static('images/photos/aid-packing.jpg'),
        'community_care': static('images/photos/community-care.jpg'),
        'outdoor_aid': static('images/photos/outdoor-aid.jpg'),
        'donation_work': static('images/photos/donation-work.jpg'),
        'default_initiative': static('images/photos/default-initiative.jpg'),
    }
    manifest = getattr(settings, 'DESIGN_ASSETS_MANIFEST', None)
    if manifest and manifest.exists():
        try:
            cloudinary_urls = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            cloudinary_urls = {}
        fallbacks.update({key: value for key, value in cloudinary_urls.items() if value})
    return {'design_assets': fallbacks}
