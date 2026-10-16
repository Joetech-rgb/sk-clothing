from django.urls import path

from . import views

urlpatterns = [
    path("webhook/paystack/", views.paystack_webhook, name="paystack-webhook"),
]
