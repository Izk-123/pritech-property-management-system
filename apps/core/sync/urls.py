from django.urls import path
from . import views

app_name = 'sync'

urlpatterns = [
    path('', views.SyncView.as_view(), name='sync'),
]