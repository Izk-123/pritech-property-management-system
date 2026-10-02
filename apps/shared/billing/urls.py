from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.BillingDashboardView.as_view(), name='dashboard'),
    path('plans/', views.PlanListView.as_view(), name='plans'),
    path('plans/<int:plan_id>/change/',
         views.ChangePlanView.as_view(), name='change_plan'),
    path('cancel/', views.CancelSubscriptionView.as_view(), name='cancel'),
    path('invoice/<int:invoice_id>/pay/',
         views.PayInvoiceView.as_view(), name='pay_invoice'),
    path('invoice/<int:invoice_id>/pdf/',
         views.InvoicePDFView.as_view(), name='invoice_pdf'),
    path('paychangu/callback/',
         views.paychangu_callback, name='paychangu_callback'),
]