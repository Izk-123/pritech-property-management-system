from django.urls import path
from . import views

app_name = 'housekeeping'

urlpatterns = [
    path('tasks/', views.TaskListView.as_view(), name='tasks'),
    path('tasks/<int:pk>/status/', views.TaskStatusUpdateView.as_view(),
         name='task_status'),
]