from django.contrib import admin 
from django.urls import path 
from drf_spectacular.views import SpectacularAPIView 
from config.views import health 
 
urlpatterns = [ 
    path("admin/", admin.site.urls), 
    path("api/v1/health/", health), 
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"), 
] 
