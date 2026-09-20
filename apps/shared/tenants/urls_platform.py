from django.urls import path
from . import views_platform

app_name = 'platform'

urlpatterns = [
    path('tenants/', views_platform.TenantListView.as_view(), name='tenant_list'),
    path('tenants/new/', views_platform.TenantCreateView.as_view(), name='tenant_create'),
    path('tenants/<int:pk>/', views_platform.TenantDetailView.as_view(), name='tenant_detail'),
    path('tenants/<int:pk>/edit/', views_platform.TenantUpdateView.as_view(), name='tenant_update'),
    path('tenants/<int:pk>/suspend/', views_platform.TenantSuspendView.as_view(), name='tenant_suspend'),
    path('tenants/<int:pk>/reactivate/', views_platform.TenantReactivateView.as_view(), name='tenant_reactivate'),
    path('tenants/<int:pk>/delete/', views_platform.TenantDeleteView.as_view(), name='tenant_delete'),
]