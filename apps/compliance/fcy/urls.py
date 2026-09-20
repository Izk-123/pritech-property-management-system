from django.urls import path
from . import views

app_name = 'fcy'

urlpatterns = [
    path('', views.FCYDashboardView.as_view(), name='dashboard'),
    path('returns/', views.RBMReturnListView.as_view(), name='rbm_return_list'),
    path('returns/generate/', views.RBMReturnGenerateView.as_view(),
         name='rbm_return_generate'),
    path('returns/<int:pk>/submitted/',
         views.RBMReturnMarkSubmittedView.as_view(),
         name='rbm_return_mark_submitted'),
]