from django.urls import path
from . import views

app_name = 'billing_admin'

urlpatterns = [
    path('', views.AdminSubscriptionListView.as_view(), name='admin_list'),
    path('invoice/<int:invoice_id>/mark-paid/',
         views.AdminMarkPaidView.as_view(), name='mark_paid'),
]
