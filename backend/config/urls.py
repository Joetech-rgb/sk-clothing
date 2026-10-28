from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from config import views

handler404 = "config.api_errors.not_found"
handler500 = "config.api_errors.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", views.health),
    path("api/v1/health/ready/", views.ready),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/auth/", include("apps.identity.urls")),
    path("api/v1/catalog/", include("apps.catalog.urls")),
    path("api/v1/delivery/", include("apps.delivery.urls")),
    path("api/v1/payments/", include("apps.payments.urls")),
]
