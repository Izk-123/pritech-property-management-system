from django.urls import path
from . import views

app_name = 'communications'

urlpatterns = [
    # Meta webhooks (public, no auth)
    path('whatsapp/webhook/', views.whatsapp_webhook, name='whatsapp_webhook'),
    path('whatsapp/verify/', views.whatsapp_verify, name='whatsapp_verify'),

    # Staff-facing
    path('logs/', views.NotificationLogListView.as_view(), name='log_list'),
    path('logs/<int:pk>/', views.NotificationLogDetailView.as_view(), name='log_detail'),
    path('inbound/', views.InboundMessageListView.as_view(), name='inbound_list'),
    path('inbound/<int:pk>/reply/', views.InboundMessageReplyView.as_view(), name='inbound_reply'),
    path('templates/', views.NotificationTemplateListView.as_view(), name='template_list'),
    path('templates/<int:pk>/', views.NotificationTemplateUpdateView.as_view(), name='template_update'),
]