from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from core.decorators import staff_required

from .models import ContentPost
from .forms import ContentPostForm

@staff_required
def post_list(request):
    posts = (
        ContentPost.objects
        .select_related("event", "cover_image")
        .all()
    )

    return render(
        request,
        "content_staff/post_list.html",
        {
            "posts": posts,
            "page_title": "Obsahové příspěvky",
        },
    )


@staff_required
def post_create(request):
    if request.method == "POST":
        form = ContentPostForm(request.POST)

        if form.is_valid():
            post = form.save(commit=False)
            post.created_by = request.user
            post.save()

            messages.success(request, "Příspěvek byl vytvořen.")
            return redirect("rozesilac:content_staff:post_list")
    else:
        form = ContentPostForm()

    return render(
        request,
        "content_staff/post_form.html",
        {
            "form": form,
            "page_title": "Nový příspěvek",
            "submit_label": "Vytvořit příspěvek",
        },
    )


@staff_required
def post_edit(request, post_id):
    post = get_object_or_404(ContentPost, id=post_id)

    if request.method == "POST":
        form = ContentPostForm(request.POST, instance=post)

        if form.is_valid():
            form.save()
            messages.success(request, "Příspěvek byl uložen.")
            return redirect("rozesilac:content_staff:post_list")
    else:
        form = ContentPostForm(instance=post)

    return render(
        request,
        "content_staff/post_form.html",
        {
            "form": form,
            "post": post,
            "page_title": f"Upravit příspěvek: {post.title}",
            "submit_label": "Uložit změny",
        },
    )