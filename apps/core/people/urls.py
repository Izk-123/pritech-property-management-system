from django.urls import path
from . import views

app_name = 'people'

urlpatterns = [
    path('', views.PersonListView.as_view(), name='list'),
    path('new/', views.PersonCreateView.as_view(), name='create'),
    path('<int:pk>/', views.PersonDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.PersonUpdateView.as_view(), name='edit'),
]