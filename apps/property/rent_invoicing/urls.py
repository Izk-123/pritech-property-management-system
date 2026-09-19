from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('', views.InvoiceListView.as_view(), name='list'),
    path('<int:pk>/', views.InvoiceDetailView.as_view(), name='detail'),
    path('lease/<int:lease_pk>/generate/',
         views.InvoiceGenerateForLeaseView.as_view(),
         name='create_for_lease'),
    path('<int:pk>/line/add/', views.InvoiceLineAddView.as_view(), name='line_add'),
    path('<int:pk>/payment/', views.InvoicePaymentView.as_view(), name='payment'),
    path('<int:pk>/apply-late-fee/', views.InvoiceApplyLateFeeView.as_view(),
         name='apply_late_fee'),
]