from django.urls import path
from . import views

app_name = 'paychangu'

urlpatterns = [
    path('webhook/', views.paychangu_webhook, name='webhook'),
    path('transactions/', views.PayChanguTransactionListView.as_view(),
         name='transaction_list'),
]