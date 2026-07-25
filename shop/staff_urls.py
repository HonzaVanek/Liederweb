from django.urls import path

from . import views


app_name = "shop_staff"

urlpatterns = [
    path("produkty/", views.staff_product_list, name="product_list"),
    path("produkty/novy/", views.staff_product_create, name="product_create"),
    path("produkty/<int:product_id>/upravit/", views.staff_product_edit, name="product_edit"),
    path("objednavky/", views.staff_order_list, name="order_list"),
    path("objednavky/<int:order_id>/", views.staff_order_detail, name="order_detail"),
    path("objednavky/<int:order_id>/stavy/", views.staff_order_update_states, name="order_update_states"),
    path("objednavky/<int:order_id>/stornovat/", views.staff_order_cancel, name="order_cancel"),
]