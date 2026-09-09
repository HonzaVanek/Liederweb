from django.urls import path

from . import views


app_name = "shop"

urlpatterns = [
    path("", views.shop_home, name="home"),

    path("obchodni-podminky/", views.terms, name="terms"),
    path("obchodni-podminky/verze/<int:version>/", views.terms_version, name="terms_version"),
    path("ochrana-osobnich-udaju/", views.privacy, name="privacy"),
    path("ochrana-osobnich-udaju/verze/<int:version>/", views.privacy_version, name="privacy_version"),

    path("kosik/", views.cart_detail, name="cart_detail"),
    path("kosik/pridat/<slug:slug>/", views.cart_add, name="cart_add"),
    path("kosik/upravit/<int:variant_id>/", views.cart_update, name="cart_update"),
    path("kosik/odebrat/<int:variant_id>/", views.cart_remove, name="cart_remove"),
    
    path("objednavka/", views.checkout, name="checkout"),
    path("objednavka/hotovo/<uuid:token>/", views.order_success, name="order_success"),
    path("objednavka/<uuid:token>/faktura/", views.order_invoice_pdf, name="order_invoice_pdf"),

    path("stazeni/<uuid:token>/", views.digital_downloads, name="digital_downloads"),
    path("stazeni/<uuid:token>/soubor/<int:grant_id>/", views.digital_download_file, name="digital_download_file"),
    
    path("<slug:slug>/", views.product_detail, name="product_detail"),
]