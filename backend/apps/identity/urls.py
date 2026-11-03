from django.urls import path

from . import views

urlpatterns = [
    path("code/request/", views.RequestCodeView.as_view(), name="auth-code-request"),
    path("code/verify/", views.VerifyCodeView.as_view(), name="auth-code-verify"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
]
