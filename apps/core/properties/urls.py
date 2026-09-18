from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    path('', views.PropertyListView.as_view(), name='list'),
    path('<int:pk>/', views.PropertyDetailView.as_view(), name='detail'),
    path('units/<int:pk>/partial/', views.UnitDetailPartialView.as_view(),
         name='unit_partial'),
]