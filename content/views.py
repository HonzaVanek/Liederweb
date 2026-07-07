import re

from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import ContentPost


def _published_posts_queryset():
    return (
        ContentPost.objects
        .filter(is_published=True)
        .select_related("event", "cover_image")
        .order_by("-published_at", "-created_at")
    )


def post_list(request):
    query = request.GET.get("q", "").strip()

    published_posts = _published_posts_queryset()

    search_results = ContentPost.objects.none()

    if query:
        search_results = published_posts

        tokens = [
            token.strip()
            for token in re.split(r"\s+", query)
            if token.strip()
        ]

        for token in tokens:
            search_results = search_results.filter(
                Q(title__icontains=token)
                | Q(perex__icontains=token)
                | Q(keywords__icontains=token)
                | Q(blocks__text__icontains=token)
                | Q(event__title__icontains=token)
            )

        search_results = search_results.distinct()

    read_posts = published_posts[:24]
    latest_posts = published_posts[:6]

    return render(
        request,
        "content/post_list.html",
        {
            "query": query,
            "search_results": search_results,
            "read_posts": read_posts,
            "latest_posts": latest_posts,
        },
    )


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