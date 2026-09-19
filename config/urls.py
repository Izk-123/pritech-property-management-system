from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    # Public
    path('', TemplateView.as_view(template_name='pages/home.html'), name='home'),
    path('properties/', include('apps.core.properties.urls')),

    # Auth
    path('login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Staff — Hospitality
    path('reservations/', include('apps.hospitality.reservations.urls')),
    path('folios/', include('apps.hospitality.folios.urls')),
    path('housekeeping/', include('apps.hospitality.housekeeping.urls')),
    
    path('property/', include('apps.property.urls')),

    # Admin
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)