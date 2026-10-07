from django.urls import path
from . import views

app_name = 'people'

urlpatterns = [
    path('', views.PersonListView.as_view(), name='list'),
    path('new/', views.PersonCreateView.as_view(), name='create'),
    path('<int:pk>/', views.PersonDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.PersonUpdateView.as_view(), name='edit'),
    
    # HTMX guest-picker endpoints
    path('quick-search/', views.PersonQuickSearchView.as_view(), name='quick_search'),
    path('quick-create/', views.PersonQuickCreateView.as_view(), name='quick_create'),
]