from django.urls import path

from . import views


app_name = "shop_staff"

urlpatterns = [
    path("produkty/", views.staff_product_list, name="product_list"),
    path("produkty/novy/", views.staff_product_create, name="product_create"),
    path(
        "produkty/<int:product_id>/upravit/",
        views.staff_product_edit,
        name="product_edit",
    ),
]