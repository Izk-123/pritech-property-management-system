from django.urls import path
from . import views

app_name = 'tourism_levy'

urlpatterns = [
    path('report/', views.levy_report_view, name='report'),
    path('record/<int:pk>/remit/', views.LevyMarkRemittedView.as_view(),
         name='mark_remitted'),
    path('bulk-remit/', views.LevyBulkMarkRemittedView.as_view(),
         name='bulk_remit'),
]