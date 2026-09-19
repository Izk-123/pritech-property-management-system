from django.urls import path, include
from . import views

app_name = 'property'

urlpatterns = [
    path('', views.AvailabilityDashboardView.as_view(), name='dashboard'),
    path('leases/', include('apps.property.leases.urls')),
    path('invoices/', include('apps.property.rent_invoicing.urls')),
    path('maintenance/', include('apps.property.maintenance.urls')),
    path('sales/', include('apps.property.sales.urls')),
]