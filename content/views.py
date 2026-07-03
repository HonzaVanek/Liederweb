from django.shortcuts import get_object_or_404, render

from .models import ContentPost


def post_detail(request, slug):
    post = get_object_or_404(
        ContentPost.objects.prefetch_related(
            "blocks",
            "blocks__images",
            "blocks__images__image",
        ),
        slug=slug,
        is_published=True,
    )

    return render(
        request,
        "content/post_detail.html",
        {
            "post": post,
        },
    )