from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="catalog-categories"),
    path("products/", views.ProductListView.as_view(), name="catalog-products"),
    path("products/<slug:slug>/", views.ProductDetailView.as_view(), name="catalog-product"),
    path("price/", views.PriceView.as_view(), name="catalog-price"),
]
