from django.urls import path

from . import views

app_name = 'guest_portal'

urlpatterns = [
    path('<str:token>/', views.GuestLandingView.as_view(), name='home'),
]