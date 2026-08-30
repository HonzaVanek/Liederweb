from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Q, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from .decorators import shop_public_or_staff_preview
from core.decorators import staff_required
from .cart import CartQuantityError, SessionCart
from .forms import (
    ProductForm,
    ProductVariantFormSet,
    ProductVariantImageFormSet,
    AddToCartForm,
    CartQuantityForm,
    CheckoutForm,
    CancelOrderForm,
    StaffOrderStateForm,
    ShippingMethodForm,
    AlbumTrackForm
)
from .models import (
    Product,
    ProductVariant,
    ProductImage,
    ProductVariantImage,
    AlbumTrack,
    Order,
    ShippingMethod,
)
from .services.checkout import CheckoutError, create_order_from_cart
from .services.orders import OrderManagementError, update_order_states, cancel_order
from .services.payments import get_bank_transfer_payment_data
from .services.invoice_pdf import build_invoice_pdf, build_invoice_pdf_filename


def _active_variant_queryset():
    return (
        ProductVariant.objects
        .filter(is_active=True)
        .order_by("sort_order", "name")
    )


def _public_product_queryset():
    active_variants = _active_variant_queryset()

    return (
        Product.objects
        .select_related("main_image")
        .annotate(
            active_variant_count=Count(
                "variants",
                filter=Q(variants__is_active=True),
                distinct=True,
            ),
            min_price=Min(
                "variants__price",
                filter=Q(variants__is_active=True),
            ),
            max_price=Max(
                "variants__price",
                filter=Q(variants__is_active=True),
            ),
        )
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=active_variants,
                to_attr="visible_variants",
            )
        )
        .order_by("sort_order", "name")
    )


def _public_product_detail_queryset():
    variant_images = (
        ProductVariantImage.objects
        .select_related("image")
        .order_by("sort_order", "id")
    )

    product_images = (
        ProductImage.objects
        .select_related("image")
        .order_by("sort_order", "id")
    )

    active_variants = (
        ProductVariant.objects
        .filter(
            is_active=True,
            album_track__isnull=True,
        )
        .prefetch_related(
            Prefetch(
                "images",
                queryset=variant_images,
                to_attr="visible_images",
            )
        )
        .order_by("sort_order", "name")
    )

    active_tracks = (
        AlbumTrack.objects
        .filter(is_active=True)
        .select_related("purchase_variant")
        .order_by("track_number", "id")
    )

    return (
        Product.objects
        .select_related("main_image")
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=active_variants,
                to_attr="visible_variants",
            ),
            Prefetch(
                "additional_images",
                queryset=product_images,
                to_attr="gallery_images",
            ),
            Prefetch(
                "tracks",
                queryset=active_tracks,
                to_attr="visible_tracks",
            ),
        )
    )

@shop_public_or_staff_preview
def shop_home(request):
    products = _public_product_queryset()

    # Staff může kontrolovat i rozpracované produkty.
    # Veřejnost smí vidět pouze publikované.
    if not request.user.is_staff:
        products = products.filter(is_published=True)

    shop_public_enabled = getattr(
        settings,
        "SHOP_PUBLIC_ENABLED",
        False,
    )

    return render(
        request,
        "shop/shop_home.html",
        {
            "products": products,
            "shop_preview_mode": not shop_public_enabled,
            "cart_item_count": len(SessionCart(request)),
        },
    )


@shop_public_or_staff_preview
def product_detail(request, slug):
    products = _public_product_detail_queryset()

    if not request.user.is_staff:
        products = products.filter(is_published=True)

    product = get_object_or_404(
        products,
        slug=slug,
    )

    shop_public_enabled = getattr(
        settings,
        "SHOP_PUBLIC_ENABLED",
        False,
    )

    return render(
        request,
        "shop/product_detail.html",
        {
            "product": product,
            "cart_item_count": len(SessionCart(request)),
            "shop_preview_mode": not shop_public_enabled,
        },
    )

@staff_required
def staff_product_list(request):
    products = (
        Product.objects
        .select_related("main_image")
        .annotate(
            variant_count=Count(
                "variants",
                distinct=True,
            ),
            active_variant_count=Count(
                "variants",
                filter=Q(variants__is_active=True),
                distinct=True,
            ),
            min_price=Min(
                "variants__price",
                filter=Q(variants__is_active=True),
            ),
            max_price=Max(
                "variants__price",
                filter=Q(variants__is_active=True),
            ),
        )
        .order_by("sort_order", "name")
    )

    return render(
        request,
        "shop/staff_product_list.html",
        {
            "products": products,
        },
    )

def _attach_variant_image_formsets(
    variant_formset,
    *,
    data=None,
):
    image_formsets = []

    for variant_form in variant_formset.forms:
        variant = variant_form.instance

        if not variant.pk:
            variant_form.image_formset = None
            continue

        image_formset = ProductVariantImageFormSet(
            data,
            instance=variant,
            prefix=f"variant-{variant.pk}-images",
        )

        variant_form.image_formset = image_formset
        image_formsets.append(
            (variant_form, image_formset)
        )

    return image_formsets


@staff_required
def staff_product_create(request):
    product = Product()

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            instance=product,
        )
        variant_formset = ProductVariantFormSet(
            request.POST,
            instance=product,
            prefix="variants",
        )

        if form.is_valid() and variant_formset.is_valid():
            with transaction.atomic():
                product = form.save()

                variant_formset.instance = product
                variant_formset.save()

            messages.success(
                request,
                f'Produkt „{product.name}“ byl vytvořen.',
            )
            return redirect(
                "shop_staff:product_edit",
                product_id=product.id,
            )

    else:
        form = ProductForm(instance=product)
        variant_formset = ProductVariantFormSet(
            instance=product,
            prefix="variants",
        )

    return render(
        request,
        "shop/staff_product_form.html",
        {
            "form": form,
            "variant_formset": variant_formset,
            "product": product,
            "page_title": "Nový produkt",
            "submit_label": "Vytvořit produkt",
        },
    )


@staff_required
def staff_product_edit(request, product_id):
    product = get_object_or_404(
        Product.objects.prefetch_related(
            "variants__images__image",
        ),
        id=product_id,
    )

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            instance=product,
        )

        variant_formset = ProductVariantFormSet(
            request.POST,
            instance=product,
            prefix="variants",
        )

        image_formsets = _attach_variant_image_formsets(
            variant_formset,
            data=request.POST,
        )

        form_valid = form.is_valid()
        variants_valid = variant_formset.is_valid()

        images_valid = True

        if variants_valid:
            for variant_form, image_formset in image_formsets:

                # Pokud se celá varianta maže,
                # její obrázky už nemusíme validovat.
                if variant_form.cleaned_data.get("DELETE"):
                    continue

                if not image_formset.is_valid():
                    images_valid = False

        if form_valid and variants_valid and images_valid:
            with transaction.atomic():
                product = form.save()

                variant_formset.instance = product
                variant_formset.save()

                for variant_form, image_formset in image_formsets:
                    if variant_form.cleaned_data.get("DELETE"):
                        continue

                    image_formset.save()

            messages.success(
                request,
                f'Produkt „{product.name}“ byl upraven.',
            )

            return redirect(
                "shop_staff:product_edit",
                product_id=product.id,
            )

    else:
        form = ProductForm(instance=product)

        variant_formset = ProductVariantFormSet(
            instance=product,
            prefix="variants",
        )

        _attach_variant_image_formsets(
            variant_formset,
        )

    return render(
        request,
        "shop/staff_product_form.html",
        {
            "form": form,
            "variant_formset": variant_formset,
            "product": product,
            "page_title": f"Upravit produkt: {product.name}",
            "submit_label": "Uložit změny",
        },
    )


@staff_required
def staff_product_track_list(request, product_id):
    product = get_object_or_404(
        Product.objects.prefetch_related(
            "tracks__purchase_variant",
        ),
        id=product_id,
    )

    return render(
        request,
        "shop/staff_product_track_list.html",
        {
            "product": product,
            "tracks": product.tracks.all(),
        },
    )


@staff_required
def staff_product_track_create(request, product_id):
    product = get_object_or_404(
        Product,
        id=product_id,
    )

    if request.method == "POST":
        form = AlbumTrackForm(
            request.POST,
            request.FILES,
            product=product,
        )

        if form.is_valid():
            track = form.save(commit=False)
            track.product = product
            track.save()

            messages.success(
                request,
                f'Stopa „{track.title}“ byla vytvořena.',
            )

            return redirect(
                "shop_staff:product_track_list",
                product_id=product.id,
            )

    else:
        form = AlbumTrackForm(
            product=product,
        )

    return render(
        request,
        "shop/staff_product_track_form.html",
        {
            "form": form,
            "product": product,
            "page_title": "Přidat stopu",
        },
    )



@staff_required
def staff_product_track_edit(
    request,
    product_id,
    track_id,
):
    product = get_object_or_404(
        Product,
        id=product_id,
    )

    track = get_object_or_404(
        AlbumTrack,
        id=track_id,
        product=product,
    )

    if request.method == "POST":
        form = AlbumTrackForm(
            request.POST,
            request.FILES,
            instance=track,
            product=product,
        )

        if form.is_valid():
            track = form.save()

            messages.success(
                request,
                f'Stopa „{track.title}“ byla upravena.',
            )

            return redirect(
                "shop_staff:product_track_list",
                product_id=product.id,
            )

    else:
        form = AlbumTrackForm(
            instance=track,
            product=product,
        )

    return render(
        request,
        "shop/staff_product_track_form.html",
        {
            "form": form,
            "product": product,
            "track": track,
            "page_title": "Upravit stopu",
        },
    )




@shop_public_or_staff_preview
def cart_detail(request):
    cart = SessionCart(request)

    return render(
        request,
        "shop/cart_detail.html",
        {
            "cart": cart,
            "cart_items": cart.items,
            "cart_item_count": len(cart),
            "shop_preview_mode": not getattr(
                settings,
                "SHOP_PUBLIC_ENABLED",
                False,
            ),
        },
    )


@shop_public_or_staff_preview
@require_POST
def cart_add(request, slug):
    products = _public_product_queryset()

    if not request.user.is_staff:
        products = products.filter(is_published=True)

    product = get_object_or_404(
        products,
        slug=slug,
    )

    form = AddToCartForm(
        request.POST,
        product=product,
    )

    if not form.is_valid():
        messages.error(
            request,
            "Produkt se nepodařilo přidat do košíku.",
        )
        return redirect(
            "shop:product_detail",
            slug=product.slug,
        )

    variant = form.cleaned_data["variant"]
    quantity = form.cleaned_data["quantity"]
    cart = SessionCart(request)

    try:
        # U digitální nahrávky zatím držíme nejvýše jednu kopii.
        if variant.is_digital:
            cart.set_quantity(variant, 1)
        else:
            cart.add(variant, quantity)

    except CartQuantityError as exc:
        messages.error(request, str(exc))

        return redirect(
            "shop:product_detail",
            slug=product.slug,
        )

    messages.success(
        request,
        f"Varianta „{variant.name}“ byla přidána do košíku.",
    )

    return redirect("shop:cart_detail")


@shop_public_or_staff_preview
@require_POST
def cart_update(request, variant_id):
    cart = SessionCart(request)

    cart_item = next(
        (
            item
            for item in cart.items
            if item.variant.id == variant_id
        ),
        None,
    )

    if cart_item is None:
        messages.error(
            request,
            "Položka už v košíku není.",
        )
        return redirect("shop:cart_detail")

    form = CartQuantityForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Zadejte platné množství.",
        )
        return redirect("shop:cart_detail")

    try:
        cart.set_quantity(
            cart_item.variant,
            form.cleaned_data["quantity"],
        )
    except CartQuantityError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            "Množství bylo upraveno.",
        )

    return redirect("shop:cart_detail")


@shop_public_or_staff_preview
@require_POST
def cart_remove(request, variant_id):
    cart = SessionCart(request)
    cart.remove(variant_id)

    messages.success(
        request,
        "Položka byla z košíku odebrána.",
    )

    return redirect("shop:cart_detail")


@shop_public_or_staff_preview
def checkout(request):
    cart = SessionCart(request)
    cart_items = cart.items

    if not cart_items:
        messages.info(
            request,
            "Košík je prázdný.",
        )
        return redirect("shop:cart_detail")

    unavailable_items = [
        item
        for item in cart_items
        if not item.is_available
    ]

    if unavailable_items:
        messages.error(
            request,
            "Některé položky už nejsou v požadovaném "
            "množství skladem.",
        )
        return redirect("shop:cart_detail")

    form = CheckoutForm(
        request.POST or None,
        requires_shipping=cart.requires_shipping,
    )

    if request.method == "POST" and form.is_valid():
        try:
            order = create_order_from_cart(
                cart=cart,
                cleaned_data=form.cleaned_data,
                user=(
                    request.user
                    if request.user.is_authenticated
                    else None
                ),
                allow_unpublished=request.user.is_staff,
            )

        except CheckoutError as exc:
            form.add_error(None, str(exc))

        else:
            cart.clear()

            return redirect(
                "shop:order_success",
                token=order.public_token,
            )

    return render(
        request,
        "shop/checkout.html",
        {
            "form": form,
            "cart": cart,
            "cart_items": cart_items,
            "cart_item_count": len(cart),
            "shop_preview_mode": not getattr(
                settings,
                "SHOP_PUBLIC_ENABLED",
                False,
            ),
        },
    )


@shop_public_or_staff_preview
def order_success(request, token):
    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        public_token=token,
    )

    cart = SessionCart(request)

    payment_data = None

    if (
        order.payment_method
        == Order.PaymentMethod.BANK_TRANSFER
        and order.payment_status == Order.PaymentStatus.AWAITING
    ):
        payment_data = get_bank_transfer_payment_data(order)

    return render(
        request,
        "shop/order_success.html",
        {
            "order": order,
            "payment_data": payment_data,
            "cart_item_count": len(cart),
            "shop_preview_mode": not getattr(
                settings,
                "SHOP_PUBLIC_ENABLED",
                False,
            ),
        },
    )




@staff_required
def staff_order_list(request):
    orders = (
        Order.objects
        .select_related("user")
        .annotate(item_count=Count("items"))
        .order_by("-created_at")
    )

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    payment_status = request.GET.get(
        "payment_status",
        "",
    ).strip()
    fulfilment_status = request.GET.get(
        "fulfilment_status",
        "",
    ).strip()

    if query:
        orders = orders.filter(
            Q(number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    valid_order_statuses = {
        value
        for value, label in Order.Status.choices
    }
    valid_payment_statuses = {
        value
        for value, label in Order.PaymentStatus.choices
    }
    valid_fulfilment_statuses = {
        value
        for value, label in Order.FulfilmentStatus.choices
    }

    if status in valid_order_statuses:
        orders = orders.filter(status=status)

    if payment_status in valid_payment_statuses:
        orders = orders.filter(
            payment_status=payment_status
        )

    if fulfilment_status in valid_fulfilment_statuses:
        orders = orders.filter(
            fulfilment_status=fulfilment_status
        )

    paginator = Paginator(orders, 10)  # 10 objednávek na stránku
    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "shop/staff_order_list.html",
        {
            "page_obj": page_obj,
            "orders": page_obj.object_list,
            "query": query,
            "selected_status": status,
            "selected_payment_status": payment_status,
            "selected_fulfilment_status": (
                fulfilment_status
            ),
            "order_status_choices": Order.Status.choices,
            "payment_status_choices": (
                Order.PaymentStatus.choices
            ),
            "fulfilment_status_choices": (
                Order.FulfilmentStatus.choices
            ),
        },
    )


@staff_required
def staff_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects
        .select_related("user")
        .prefetch_related(
            "items",
            "status_history__performed_by",
        ),
        id=order_id,
    )

    payment_data = None
    if order.payment_method == Order.PaymentMethod.BANK_TRANSFER:
        payment_data = get_bank_transfer_payment_data(order)

    return render(
        request,
        "shop/staff_order_detail.html",
        {
            "order": order,
            "state_form": StaffOrderStateForm(
                order=order
            ),
            "cancel_form": CancelOrderForm(),
            "payment_data": payment_data,
        },
    )


@staff_required
@require_POST
def staff_order_update_states(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
    )

    form = StaffOrderStateForm(
        request.POST,
        order=order,
    )

    if not form.is_valid():
        messages.error(
            request,
            "Stavy objednávky se nepodařilo změnit. "
            "Zkontrolujte formulář.",
        )

        return render(
            request,
            "shop/staff_order_detail.html",
            {
                "order": (
                    Order.objects
                    .select_related("user")
                    .prefetch_related(
                        "items",
                        "status_history__performed_by",
                    )
                    .get(id=order_id)
                ),
                "state_form": form,
                "cancel_form": CancelOrderForm(),
            },
        )

    try:
        order, changed = update_order_states(
            order_id=order.id,
            order_status=form.cleaned_data[
                "order_status"
            ],
            payment_status=form.cleaned_data[
                "payment_status"
            ],
            fulfilment_status=form.cleaned_data[
                "fulfilment_status"
            ],
            note=form.cleaned_data.get("note", ""),
            performed_by=request.user,
        )

    except OrderManagementError as exc:
        messages.error(request, str(exc))
    else:
        if changed:
            messages.success(
                request,
                "Stavy objednávky byly upraveny.",
            )
        else:
            messages.info(
                request,
                "Nebyly provedeny žádné změny.",
            )

    return redirect(
        "shop_staff:order_detail",
        order_id=order_id,
    )


@staff_required
@require_POST
def staff_order_cancel(request, order_id):
    form = CancelOrderForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Vyplňte důvod storna.",
        )
        return redirect(
            "shop_staff:order_detail",
            order_id=order_id,
        )

    try:
        cancel_order(
            order_id=order_id,
            reason=form.cleaned_data["reason"],
            performed_by=request.user,
        )

    except OrderManagementError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            "Objednávka byla stornována a dostupné "
            "skladové položky byly vráceny na sklad.",
        )

    return redirect(
        "shop_staff:order_detail",
        order_id=order_id,
    )




def _invoice_pdf_response(invoice):
    pdf_bytes = build_invoice_pdf(invoice)

    response = HttpResponse(
        pdf_bytes,
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        f'inline; filename="'
        f'{build_invoice_pdf_filename(invoice)}"'
    )

    return response


@shop_public_or_staff_preview
def order_invoice_pdf(request, token):
    order = get_object_or_404(
        Order.objects.select_related("invoice"),
        public_token=token,
    )

    return _invoice_pdf_response(order.invoice)


@staff_required
def staff_order_invoice_pdf(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("invoice"),
        id=order_id,
    )

    return _invoice_pdf_response(order.invoice)


@staff_required
def staff_shipping_method_list(request):
    shipping_methods = ShippingMethod.objects.all()

    return render(
        request,
        "shop/staff_shipping_method_list.html",
        {
            "shipping_methods": shipping_methods,
        },
    )


@staff_required
def staff_shipping_method_create(request):
    if request.method == "POST":
        form = ShippingMethodForm(request.POST)

        if form.is_valid():
            shipping_method = form.save()

            messages.success(
                request,
                f'Doprava „{shipping_method.name}“ byla vytvořena.',
            )

            return redirect(
                "shop_staff:shipping_method_list"
            )
    else:
        form = ShippingMethodForm()

    return render(
        request,
        "shop/staff_shipping_method_form.html",
        {
            "form": form,
            "page_title": "Nový způsob dopravy",
        },
    )


@staff_required
def staff_shipping_method_edit(request, shipping_method_id):
    shipping_method = get_object_or_404(
        ShippingMethod,
        id=shipping_method_id,
    )

    if request.method == "POST":
        form = ShippingMethodForm(
            request.POST,
            instance=shipping_method,
        )

        if form.is_valid():
            shipping_method = form.save()

            messages.success(
                request,
                f'Doprava „{shipping_method.name}“ byla upravena.',
            )

            return redirect(
                "shop_staff:shipping_method_list"
            )
    else:
        form = ShippingMethodForm(
            instance=shipping_method,
        )

    return render(
        request,
        "shop/staff_shipping_method_form.html",
        {
            "form": form,
            "shipping_method": shipping_method,
            "page_title": "Upravit způsob dopravy",
        },
    )