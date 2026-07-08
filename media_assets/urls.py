from django.urls import path

from . import views

app_name = "media_assets"

urlpatterns = [
    path("", views.MediaAssetAdminListView.as_view(), name="asset_list"),
    path("novy/", views.MediaAssetCreateView.as_view(), name="asset_create"),
    path("bulk-upload/", views.MediaAssetBulkImageUploadView.as_view(), name="asset_bulk_upload"),
    path("<int:pk>/upravit/", views.MediaAssetUpdateView.as_view(), name="asset_update"),
    path("<int:pk>/smazat/", views.asset_delete, name="asset_delete"),
]