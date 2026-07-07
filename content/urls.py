from django.urls import path

from . import views
from . import staff_views

app_name = "content"

public_urlpatterns = [
    path("", views.post_list, name="post_list"),
    path("<slug:slug>/", views.post_detail, name="post_detail"),
]

staff_urlpatterns = [
    path("", staff_views.post_list, name="post_list"),
    path("new/", staff_views.post_create, name="post_create"),
    path("<int:post_id>/edit/", staff_views.post_edit, name="post_edit"),
    path("<int:post_id>/blocks/add/<str:block_type>/", staff_views.block_add, name="block_add"),
    path("<int:post_id>/blocks/<int:block_id>/edit/", staff_views.block_edit, name="block_edit"),
    path("<int:post_id>/blocks/<int:block_id>/delete/", staff_views.block_delete, name="block_delete"),
    path("<int:post_id>/blocks/<int:block_id>/move-up/", staff_views.block_move_up, name="block_move_up"),
    path("<int:post_id>/blocks/<int:block_id>/move-down/", staff_views.block_move_down, name="block_move_down"),
    path("<int:post_id>/blocks/<int:block_id>/images/add/", staff_views.block_image_add, name="block_image_add"),
    path("<int:post_id>/blocks/<int:block_id>/images/<int:image_id>/delete/", staff_views.block_image_delete, name="block_image_delete"),
    path("<int:post_id>/blocks/<int:block_id>/images/<int:image_id>/move-up/", staff_views.block_image_move_up, name="block_image_move_up"),
    path("<int:post_id>/blocks/<int:block_id>/images/<int:image_id>/move-down/", staff_views.block_image_move_down, name="block_image_move_down"),
    path("<int:post_id>/blocks/<int:block_id>/images/<int:image_id>/edit/", staff_views.block_image_edit, name="block_image_edit"),
]

urlpatterns = public_urlpatterns