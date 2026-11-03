from django.urls import path

from . import views

urlpatterns = [
    path("", views.CheckoutView.as_view(), name="orders-checkout"),
    path("lookup/", views.OrderLookupView.as_view(), name="orders-lookup"),
]
