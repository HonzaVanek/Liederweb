from django.urls import path

from . import views


app_name = "shop_staff"

urlpatterns = [
    path("private/<path:path>", views.staff_private_file, name="private_file"),
    path("produkty/", views.staff_product_list, name="product_list"),
    path("produkty/novy/", views.staff_product_create, name="product_create"),
    path("produkty/<int:product_id>/upravit/", views.staff_product_edit, name="product_edit"),
    # Stopy digitálního alba
    path("produkty/<int:product_id>/stopy/", views.staff_product_track_list, name="product_track_list"),
    path("produkty/<int:product_id>/stopy/nova/", views.staff_product_track_create, name="product_track_create"),
    path("produkty/<int:product_id>/stopy/<int:track_id>/upravit/", views.staff_product_track_edit, name="product_track_edit"),        
    path("objednavky/", views.staff_order_list, name="order_list"),
    path("objednavky/<int:order_id>/", views.staff_order_detail, name="order_detail"),
    path("objednavky/<int:order_id>/stavy/", views.staff_order_update_states, name="order_update_states"),
    path("objednavky/<int:order_id>/stornovat/", views.staff_order_cancel, name="order_cancel"),
    path("objednavky/<int:order_id>/faktura/", views.staff_order_invoice_pdf, name="order_invoice_pdf"),
    path("doprava/", views.staff_shipping_method_list, name="shipping_method_list"),
    path("doprava/nova/", views.staff_shipping_method_create, name="shipping_method_create"),
    path("doprava/<int:shipping_method_id>/upravit/", views.staff_shipping_method_edit, name="shipping_method_edit"),
]