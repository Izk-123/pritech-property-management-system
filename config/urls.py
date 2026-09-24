from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView
from apps.shared.users.views import SchemaAwareLoginView


urlpatterns = [
    path('', TemplateView.as_view(template_name='pages/home.html'), name='home'),
    
    # PWA manifest and service worker
    path('', include('pwa.urls')),
    
    # config/urls.py and config/urls_public.py
    path('offline/', TemplateView.as_view(template_name='pages/offline.html'),
        name='offline'),

    # Core
    path('properties/', include('apps.core.properties.urls')),
    path('people/', include('apps.core.people.urls')),
    path('documents/', include('apps.core.documents.urls')),

    # Auth
    path('login/', SchemaAwareLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Hospitality
    path('reservations/', include('apps.hospitality.reservations.urls')),
    path('folios/', include('apps.hospitality.folios.urls')),
    path('housekeeping/', include('apps.hospitality.housekeeping.urls')),

    # Property
    path('property/', include('apps.property.urls')),

    # Compliance
    path('compliance/', include('apps.compliance.urls')),
    
    path('api/v1/sync/', include('apps.core.sync.urls')),
    
    # Communications (staff-facing)
    path('communications/', include('apps.communications.urls')),

    # Admin
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)