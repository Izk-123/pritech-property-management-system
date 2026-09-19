from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    path('', views.ListingListView.as_view(), name='listing_list'),
    path('new/', views.ListingCreateView.as_view(), name='listing_create'),
    path('<int:pk>/', views.ListingDetailView.as_view(), name='listing_detail'),
    path('<int:listing_pk>/offer/new/',
         views.OfferCreateView.as_view(), name='offer_create'),
    path('offer/<int:pk>/accept/',
         views.OfferAcceptView.as_view(), name='offer_accept'),
    path('offer/<int:offer_pk>/agreement/new/',
         views.AgreementCreateView.as_view(), name='agreement_create'),
    path('agreement/<int:pk>/',
         views.AgreementDetailView.as_view(), name='agreement_detail'),
    path('agreement/<int:pk>/complete/',
         views.AgreementCompleteView.as_view(), name='agreement_complete'),
]