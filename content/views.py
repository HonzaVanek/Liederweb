import re

from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import ContentPost, ContentGallery


def _published_posts_queryset():
    return (
        ContentPost.objects
        .filter(is_published=True)
        .select_related("event", "cover_image")
        .order_by("-published_at", "-created_at")
    )


def _published_galleries_queryset():
    return (
        ContentGallery.objects
        .filter(is_published=True)
        .select_related("event", "cover_image")
        .prefetch_related("images", "images__image")
        .order_by("-published_at", "-created_at")
    )


def _build_latest_items(posts, galleries, limit=8):
    latest_items = []

    for post in posts[:limit]:
        latest_items.append({
            "type": "Článek",
            "title": post.title,
            "url": post.get_absolute_url(),
            "date": post.published_at or post.created_at,
        })

    for gallery in galleries[:limit]:
        latest_items.append({
            "type": "Fotogalerie",
            "title": gallery.title,
            "url": gallery.get_absolute_url(),
            "date": gallery.published_at or gallery.created_at,
        })

    return sorted(
        latest_items,
        key=lambda item: item["date"],
        reverse=True,
    )[:limit]


def post_list(request):
    """
    Landing page Objevujte.
    Nezobrazuje kompletní archivy, jen kompaktní náhledy.
    """
    query = request.GET.get("q", "").strip()

    published_posts = _published_posts_queryset()
    published_galleries = _published_galleries_queryset()

    search_results = ContentPost.objects.none()
    gallery_search_results = ContentGallery.objects.none()

    if query:
        tokens = [
            token.strip()
            for token in re.split(r"\s+", query)
            if token.strip()
        ]

        search_results = published_posts
        gallery_search_results = published_galleries

        for token in tokens:
            search_results = search_results.filter(
                Q(title__icontains=token)
                | Q(perex__icontains=token)
                | Q(keywords__icontains=token)
                | Q(blocks__text__icontains=token)
                | Q(event__title__icontains=token)
            )

            gallery_search_results = gallery_search_results.filter(
                Q(title__icontains=token)
                | Q(description__icontains=token)
                | Q(event__title__icontains=token)
                | Q(images__caption__icontains=token)
                | Q(images__alt_text__icontains=token)
            )

        search_results = search_results.distinct()
        gallery_search_results = gallery_search_results.distinct()

    read_posts = published_posts[:4]
    galleries = published_galleries[:4]
    latest_items = _build_latest_items(published_posts, published_galleries, limit=8)

    return render(
        request,
        "content/post_list.html",
        {
            "query": query,
            "search_results": search_results,
            "gallery_search_results": gallery_search_results,
            "read_posts": read_posts,
            "galleries": galleries,
            "latest_items": latest_items,
            "post_count": published_posts.count(),
            "gallery_count": published_galleries.count(),
        },
    )


def post_archive(request):
    """
    Plný výpis článků.
    """
    posts = _published_posts_queryset()

    return render(
        request,
        "content/post_archive.html",
        {
            "posts": posts,
        },
    )


def gallery_list(request):
    """
    Plný výpis fotogalerií.
    """
    galleries = _published_galleries_queryset()

    return render(
        request,
        "content/gallery_list.html",
        {
            "galleries": galleries,
        },
    )


def gallery_detail(request, slug):
    gallery = get_object_or_404(
        ContentGallery.objects
        .select_related("event", "cover_image")
        .prefetch_related("images", "images__image"),
        slug=slug,
        is_published=True,
    )

    images = gallery.images.select_related("image").all()

    return render(
        request,
        "content/gallery_detail.html",
        {
            "gallery": gallery,
            "images": images,
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
