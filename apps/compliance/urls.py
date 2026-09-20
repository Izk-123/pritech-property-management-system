from django.urls import path, include
from . import views

app_name = 'compliance'

urlpatterns = [
    path('', views.ComplianceDashboardView.as_view(), name='dashboard'),
    path('eis/', include('apps.compliance.eis.urls')),
    path('paychangu/', include('apps.compliance.paychangu.urls')),
    path('levy/', include('apps.compliance.tourism_levy.urls')),
    path('forex/', include('apps.compliance.forex.urls')),
    path('fcy/', include('apps.compliance.fcy.urls')),
]