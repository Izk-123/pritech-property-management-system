from django.urls import path
from . import views

app_name = 'pdf'

urlpatterns = [
    path('folio/<int:pk>/', views.FolioInvoicePDFView.as_view(),
         name='folio_invoice'),
    path('receipt/<int:pk>/', views.PaymentReceiptPDFView.as_view(),
         name='payment_receipt'),
    path('lease/<int:pk>/', views.LeaseAgreementPDFView.as_view(),
         name='lease_agreement'),
    path('rent-invoice/<int:pk>/', views.RentInvoicePDFView.as_view(),
         name='rent_invoice'),
    path('sale/<int:pk>/', views.SaleAgreementPDFView.as_view(),
         name='sale_agreement'),
]