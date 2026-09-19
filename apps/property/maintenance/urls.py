from django.urls import path
from . import views

app_name = 'maintenance'

urlpatterns = [
    path('', views.MaintenanceListView.as_view(), name='list'),
    path('new/', views.MaintenanceCreateView.as_view(), name='create'),
    path('<int:pk>/', views.MaintenanceDetailView.as_view(), name='detail'),
    path('<int:pk>/assign/', views.MaintenanceAssignView.as_view(), name='assign'),
    path('<int:pk>/complete/', views.MaintenanceCompleteView.as_view(), name='complete'),
    path('<int:pk>/status/', views.MaintenanceStatusUpdateView.as_view(), name='status'),
]