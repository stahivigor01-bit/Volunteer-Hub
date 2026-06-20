import json
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.templatetags.static import static

from .models import Message


def header_stats(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'unread_notifications_count': 0, 'unread_messages_count': 0}

    cache_key = f'header-stats:{user.id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    unread_notifications = user.notifications.filter(is_read=False).count()
    unread_messages_qs = Message.objects.filter(is_read=False).exclude(sender=user)
    if user.is_platform_admin or user.is_org_manager:
        unread_messages = unread_messages_qs.count()
    else:
        unread_messages = unread_messages_qs.filter(
            Q(thread__volunteer=user) | Q(thread__coordinator=user)
        ).count()

    stats = {
        'unread_notifications_count': unread_notifications,
        'unread_messages_count': unread_messages,
    }
    cache.set(cache_key, stats, 8)
    return stats


@lru_cache(maxsize=1)
def design_asset_urls():
    local_fallback = static('images/og-preview.png')
    fallbacks = {
        'hero_volunteers': local_fallback,
        'aid_packing': local_fallback,
        'community_care': local_fallback,
        'outdoor_aid': local_fallback,
        'donation_work': local_fallback,
        'default_initiative': local_fallback,
    }
    manifest = getattr(settings, 'DESIGN_ASSETS_MANIFEST', None)
    if manifest and manifest.exists():
        try:
            cloudinary_urls = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            cloudinary_urls = {}
        fallbacks.update({key: value for key, value in cloudinary_urls.items() if value})
        cloudinary_fallback = cloudinary_urls.get('hero_volunteers') or cloudinary_urls.get('aid_packing')
        if cloudinary_fallback:
            for key, value in fallbacks.items():
                if value == local_fallback:
                    fallbacks[key] = cloudinary_fallback
    return fallbacks


def design_assets(request):
    return {'design_assets': design_asset_urls()}
