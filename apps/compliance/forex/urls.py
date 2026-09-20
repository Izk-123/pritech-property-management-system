from django.urls import path
from . import views

app_name = 'forex'

urlpatterns = [
    path('rates/', views.ForexRateListView.as_view(), name='rate_list'),
    path('refresh/', views.ForexRefreshView.as_view(), name='refresh'),
]