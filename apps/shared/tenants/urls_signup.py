from django.urls import path
from . import views_signup

app_name = 'signup'

urlpatterns = [
    path('', views_signup.TenantSignupView.as_view(), name='signup'),
    path('success/', views_signup.SignupSuccessView.as_view(), name='signup_success'),
]