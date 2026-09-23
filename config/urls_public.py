from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView
from apps.shared.tenants import views_signup
from apps.shared.users.views import SchemaAwareLoginView


urlpatterns = [
    # Marketing home
    path('', TemplateView.as_view(template_name='pages/public_home.html'),
         name='public_home'),
    
    # PWA manifest and service worker
    path('', include('pwa.urls')),
    
    # config/urls.py and config/urls_public.py
    path('offline/', TemplateView.as_view(template_name='pages/offline.html'),
        name='offline'),

    # Signup
    path('signup/', include('apps.shared.tenants.urls_signup')),

    # Platform admin (tenant management)
    path('platform/', include('apps.shared.tenants.urls_platform')),

    # Auth
    path('login/', SchemaAwareLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Health check
    path('health/', views_signup.HealthCheckView.as_view(), name='health'),

    # Admin
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)