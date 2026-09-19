from django.urls import path
from . import views

app_name = 'folios'

urlpatterns = [
    path('<int:pk>/charge/', views.FolioChargeCreateView.as_view(), name='charge'),
    path('<int:pk>/payment/', views.FolioPaymentCreateView.as_view(), name='payment'),
]