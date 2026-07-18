from django.urls import path

from . import views


app_name = "shop"

urlpatterns = [
    path("", views.shop_home, name="home"),

    path("kosik/", views.cart_detail, name="cart_detail"),
    path("kosik/pridat/<slug:slug>/", views.cart_add, name="cart_add"),
    path("kosik/upravit/<int:variant_id>/", views.cart_update, name="cart_update"),
    path("kosik/odebrat/<int:variant_id>/", views.cart_remove, name="cart_remove"),
    
    path("objednavka/", views.checkout, name="checkout"),
    path("objednavka/hotovo/<uuid:token>/", views.order_success, name="order_success"),
    
    path("<slug:slug>/", views.product_detail, name="product_detail"),
]