from django.urls import path
from . import views

app_name = 'billing_admin'

urlpatterns = [
    path('', views.AdminSubscriptionListView.as_view(), name='admin_list'),
    path('<int:pk>/', views.AdminSubscriptionDetailView.as_view(),
         name='admin_detail'),
    path('invoice/<int:invoice_id>/mark-paid/',
         views.AdminMarkPaidView.as_view(), name='mark_paid'),
    path('<int:pk>/extend-trial/',
         views.AdminExtendTrialView.as_view(), name='extend_trial'),
]