from django.urls import path

from . import views

urlpatterns = [
    path("stations/", views.StationListView.as_view(), name="delivery-stations"),
    path("quote/", views.QuoteView.as_view(), name="delivery-quote"),
]
