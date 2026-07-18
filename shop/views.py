from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Min, Q, Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import shop_public_or_staff_preview
from core.decorators import staff_required

from .forms import ProductForm, ProductVariantFormSet
from .models import Product, ProductVariant



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