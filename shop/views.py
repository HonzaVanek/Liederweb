from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Q, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import shop_public_or_staff_preview
from core.decorators import staff_required
from .cart import CartQuantityError, SessionCart
from .forms import ProductForm, ProductVariantFormSet, AddToCartForm, CartQuantityForm, CheckoutForm, CancelOrderForm, StaffOrderStateForm
from .models import Product, ProductVariant, Order
from .services.checkout import CheckoutError, create_order_from_cart
from .services.orders import OrderManagementError, update_order_states, cancel_order
from .services.payments import get_bank_transfer_payment_data


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
    products = _public_product_queryset()

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
            return redirect("shop_staff:product_list")

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
        Product.objects.prefetch_related("variants"),
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

        if form.is_valid() and variant_formset.is_valid():
            with transaction.atomic():
                product = form.save()
                variant_formset.save()

            messages.success(
                request,
                f'Produkt „{product.name}“ byl upraven.',
            )
            return redirect("shop_staff:product_list")

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
            "page_title": f"Upravit produkt: {product.name}",
            "submit_label": "Uložit změny",
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