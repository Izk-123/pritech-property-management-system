from django.urls import path
from . import views

app_name = 'reservations'

urlpatterns = [
    path('', views.ReservationListView.as_view(), name='list'),
    path('front-desk/', views.FrontDeskDashboardView.as_view(), name='front_desk'),
    path('new/', views.ReservationCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ReservationDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ReservationUpdateView.as_view(), name='edit'),
    path('<int:pk>/cancel/', views.ReservationCancelView.as_view(), name='cancel'),
    path('<int:pk>/check-in/', views.CheckInView.as_view(), name='check_in'),
    path('<int:pk>/check-out/', views.CheckOutView.as_view(), name='check_out'),
]