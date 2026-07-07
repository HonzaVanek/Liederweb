from django.contrib import messages
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse

from core.decorators import staff_required

from .forms import ContentBlockForm, ContentBlockImageForm, ContentPostForm
from .models import ContentBlock, ContentBlockImage, ContentPost
from events.models import Event


def _next_block_position(post):
    max_position = post.blocks.aggregate(max_position=Max("position"))["max_position"]
    return (max_position or 0) + 10


def _next_image_position(block):
    max_position = block.images.aggregate(max_position=Max("position"))["max_position"]
    return (max_position or 0) + 10


def _get_post(post_id):
    return get_object_or_404(ContentPost, id=post_id)


def _get_block(post, block_id):
    return get_object_or_404(ContentBlock, id=block_id, post=post)


def _get_block_image(block, image_id):
    return get_object_or_404(ContentBlockImage, id=image_id, block=block)

def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


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
    initial = {}

    event_id = request.GET.get("event_id")

    if event_id:
        event = Event.objects.filter(id=event_id).first()

        if event:
            initial["event"] = event

    if request.method == "POST":
        form = ContentPostForm(request.POST)

        if form.is_valid():
            post = form.save(commit=False)
            post.created_by = request.user
            post.save()

            messages.success(request, "Příspěvek byl vytvořen. Teď můžeš přidat obsahové bloky.")
            return redirect("rozesilac:content_staff:post_edit", post_id=post.id)
    else:
        form = ContentPostForm(initial=initial)

    return render(
        request,
        "content_staff/post_form.html",
        {
            "form": form,
            "post": None,
            "page_title": "Nový příspěvek",
            "submit_label": "Vytvořit příspěvek",
        },
    )


@staff_required
def post_edit(request, post_id):
    post = get_object_or_404(
        ContentPost.objects
        .select_related("event", "cover_image")
        .prefetch_related("blocks", "blocks__images", "blocks__images__image"),
        id=post_id,
    )

    if request.method == "POST":
        form = ContentPostForm(request.POST, instance=post)

        if form.is_valid():
            form.save()
            messages.success(request, "Příspěvek byl uložen.")
            return redirect("rozesilac:content_staff:post_edit", post_id=post.id)
    else:
        form = ContentPostForm(instance=post)

    blocks = post.blocks.prefetch_related("images", "images__image").all()

    return render(
        request,
        "content_staff/post_form.html",
        {
            "form": form,
            "post": post,
            "blocks": blocks,
            "page_title": f"Upravit příspěvek: {post.title}",
            "submit_label": "Uložit změny",
        },
    )


@staff_required
def block_add(request, post_id, block_type):
    post = _get_post(post_id)

    allowed_types = {
        ContentBlock.BLOCK_TEXT,
        ContentBlock.BLOCK_GALLERY,
        ContentBlock.BLOCK_YOUTUBE,
        ContentBlock.BLOCK_CTA,
    }

    if block_type not in allowed_types:
        messages.error(request, "Neznámý typ bloku.")
        return redirect("rozesilac:content_staff:post_edit", post_id=post.id)

    if request.method != "POST":
        return redirect("rozesilac:content_staff:post_edit", post_id=post.id)

    block = ContentBlock.objects.create(
        post=post,
        block_type=block_type,
        position=_next_block_position(post),
    )

    messages.success(request, "Blok byl přidán.")
    return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)


@staff_required
def block_edit(request, post_id, block_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)

    if request.method == "POST":
        form = ContentBlockForm(
            request.POST,
            instance=block,
            block_type=block.block_type,
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Blok byl uložen.")
            return redirect("rozesilac:content_staff:post_edit", post_id=post.id)
    else:
        form = ContentBlockForm(instance=block, block_type=block.block_type)

    is_gallery = block.block_type == ContentBlock.BLOCK_GALLERY

    image_form = None
    images = None

    if is_gallery:
        image_form = ContentBlockImageForm()
        images = list(block.images.select_related("image").all())

        for image_item in images:
            image_item.edit_form = ContentBlockImageForm(
                instance=image_item,
                prefix=f"image-{image_item.id}",
            )

    return render(
        request,
        "content_staff/block_form.html",
        {
            "post": post,
            "content_block": block,
            "form": form,
            "image_form": image_form,
            "images": images,
            "is_gallery": is_gallery,
            "page_title": f"Upravit blok: {block.get_block_type_display()}",
            "submit_label": "Uložit blok",
        },
    )


@staff_required
def block_delete(request, post_id, block_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)

    if request.method == "POST":
        block.delete()
        messages.success(request, "Blok byl smazán.")

    return redirect("rozesilac:content_staff:post_edit", post_id=post.id)


@staff_required
def block_move_up(request, post_id, block_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)

    moved = False

    previous_block = (
        post.blocks
        .filter(position__lt=block.position)
        .order_by("-position", "-id")
        .first()
    )

    if request.method == "POST" and previous_block:
        block.position, previous_block.position = previous_block.position, block.position
        block.save(update_fields=["position"])
        previous_block.save(update_fields=["position"])
        moved = True

    if _is_ajax(request):
        return JsonResponse({
            "ok": True,
            "moved": moved,
            "direction": "up",
            "block_id": block.id,
        })

    return redirect("rozesilac:content_staff:post_edit", post_id=post.id)


@staff_required
def block_move_down(request, post_id, block_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)

    moved = False

    next_block = (
        post.blocks
        .filter(position__gt=block.position)
        .order_by("position", "id")
        .first()
    )

    if request.method == "POST" and next_block:
        block.position, next_block.position = next_block.position, block.position
        block.save(update_fields=["position"])
        next_block.save(update_fields=["position"])
        moved = True

    if _is_ajax(request):
        return JsonResponse({
            "ok": True,
            "moved": moved,
            "direction": "down",
            "block_id": block.id,
        })

    return redirect("rozesilac:content_staff:post_edit", post_id=post.id)


@staff_required
def block_image_add(request, post_id, block_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)

    if block.block_type != ContentBlock.BLOCK_GALLERY:
        messages.error(request, "Obrázky lze přidávat jen do galerijního bloku.")
        return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)

    if request.method == "POST":
        form = ContentBlockImageForm(
            request.POST,
            instance=ContentBlockImage(block=block),
        )

        if form.is_valid():
            block_image = form.save(commit=False)
            block_image.block = block
            block_image.position = _next_image_position(block)
            block_image.save()

            messages.success(request, "Obrázek byl přidán.")
        else:
            messages.error(request, "Obrázek se nepodařilo přidat.")

    return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)


@staff_required
def block_image_delete(request, post_id, block_id, image_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)
    block_image = _get_block_image(block, image_id)

    if request.method == "POST":
        block_image.delete()
        messages.success(request, "Obrázek byl odebrán z galerie.")

    return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)


@staff_required
def block_image_move_up(request, post_id, block_id, image_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)
    block_image = _get_block_image(block, image_id)

    previous_image = (
        block.images
        .filter(position__lt=block_image.position)
        .order_by("-position", "-id")
        .first()
    )

    if request.method == "POST" and previous_image:
        block_image.position, previous_image.position = previous_image.position, block_image.position
        block_image.save(update_fields=["position"])
        previous_image.save(update_fields=["position"])

    return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)


@staff_required
def block_image_move_down(request, post_id, block_id, image_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)
    block_image = _get_block_image(block, image_id)

    next_image = (
        block.images
        .filter(position__gt=block_image.position)
        .order_by("position", "id")
        .first()
    )

    if request.method == "POST" and next_image:
        block_image.position, next_image.position = next_image.position, block_image.position
        block_image.save(update_fields=["position"])
        next_image.save(update_fields=["position"])

    return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)

@staff_required
def block_image_edit(request, post_id, block_id, image_id):
    post = _get_post(post_id)
    block = _get_block(post, block_id)
    block_image = _get_block_image(block, image_id)

    if block.block_type != ContentBlock.BLOCK_GALLERY:
        messages.error(request, "Obrázky lze upravovat jen u galerijního bloku.")
        return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)

    if request.method == "POST":
        form = ContentBlockImageForm(
            request.POST,
            instance=block_image,
            prefix=f"image-{block_image.id}",
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Obrázek v galerii byl uložen.")
        else:
            messages.error(request, "Obrázek se nepodařilo uložit.")

    return redirect("rozesilac:content_staff:block_edit", post_id=post.id, block_id=block.id)