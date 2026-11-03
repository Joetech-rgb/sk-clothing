from django.urls import path

from . import api, views

urlpatterns = [
    path("webhook/paystack/", views.paystack_webhook, name="paystack-webhook"),
    path("initialize/", api.InitializeView.as_view(), name="payments-initialize"),
    path("verify/", api.VerifyView.as_view(), name="payments-verify"),
]
