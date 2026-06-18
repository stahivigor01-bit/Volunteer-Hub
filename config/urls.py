from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path('healthz/', lambda request: HttpResponse('ok', content_type='text/plain')),
    path('django-admin/', admin.site.urls),
    path('', include('apps.hub.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
