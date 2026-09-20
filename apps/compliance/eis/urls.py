from django.urls import path
from . import views

app_name = 'eis'

urlpatterns = [
    path('terminals/', views.EISTerminalListView.as_view(), name='terminal_list'),
    path('terminals/<int:pk>/', views.EISTerminalDetailView.as_view(), name='terminal_detail'),
    path('terminals/<int:pk>/sync/', views.EISTerminalSyncView.as_view(), name='terminal_sync'),
    path('terminals/<int:pk>/ping/', views.EISTerminalPingView.as_view(), name='terminal_ping'),
    path('invoices/', views.EISInvoiceLogListView.as_view(), name='invoice_log'),
    path('offline-queue/', views.EISOfflineQueueView.as_view(), name='offline_queue'),
    path('force-sync/', views.EISForceSyncView.as_view(), name='force_sync'),
    path('products/', views.EISProductMappingListView.as_view(), name='product_list'),
]