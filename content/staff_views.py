from django.shortcuts import render, redirect, get_object_or_404

from core.decorators import staff_required

from .models import ContentPost


@staff_required
def post_list(request):
    posts = ContentPost.objects.select_related("event", "cover_image").all()

    return render(
        request,
        "content_staff/post_list.html",
        {
            "posts": posts,
        },
    )


@staff_required
def post_create(request):
    return render(
        request,
        "content_staff/post_form.html",
        {
            "page_title": "Nový příspěvek",
        },
    )


@staff_required
def post_edit(request, post_id):
    post = get_object_or_404(ContentPost, id=post_id)

    return render(
        request,
        "content_staff/post_form.html",
        {
            "post": post,
            "page_title": f"Upravit příspěvek: {post.title}",
        },
    )