"""
Public signup URLs.

Mounted at ``/signup/`` in config/urls_public.py::

    /signup/           → TenantSignupView         (email + password)
    /signup/complete/  → SignupCompleteView       (Google second step)
    /signup/success/   → SignupSuccessView        (thank-you page)
"""
from django.urls import path

from . import views_signup

app_name = 'signup'

urlpatterns = [
    path('', views_signup.TenantSignupView.as_view(), name='signup'),
    path('complete/', views_signup.SignupCompleteView.as_view(), name='complete'),
    path('success/', views_signup.SignupSuccessView.as_view(), name='signup_success'),
]