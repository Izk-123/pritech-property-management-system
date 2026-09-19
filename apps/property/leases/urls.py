from django.urls import path
from . import views

app_name = 'leases'

urlpatterns = [
    path('', views.LeaseListView.as_view(), name='list'),
    path('new/', views.LeaseCreateView.as_view(), name='create'),
    path('<int:pk>/', views.LeaseDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.LeaseUpdateView.as_view(), name='edit'),
    path('<int:pk>/activate/', views.LeaseActivateView.as_view(), name='activate'),
    path('<int:pk>/terminate/', views.LeaseTerminateView.as_view(), name='terminate'),
    path('<int:pk>/renew/', views.LeaseRenewView.as_view(), name='renew'),
]