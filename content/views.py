from django.shortcuts import get_object_or_404, render

from .models import ContentPost


def post_detail(request, slug):
    post = get_object_or_404(
        ContentPost.objects
        .select_related("event", "cover_image")
        .prefetch_related(
            "blocks",
            "blocks__images",
            "blocks__images__image",
        ),
        slug=slug,
        is_published=True,
    )

    blocks = post.blocks.all()

    related_posts = ContentPost.objects.none()

    if post.event_id:
        related_posts = (
            ContentPost.objects
            .filter(event=post.event, is_published=True)
            .exclude(id=post.id)
            .select_related("cover_image")
            .order_by("-published_at", "-created_at")[:3]
        )

    return render(
        request,
        "content/post_detail.html",
        {
            "post": post,
            "blocks": blocks,
            "related_posts": related_posts,
        },
    )