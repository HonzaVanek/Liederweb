from django import template

from core.models import Partner

register = template.Library()


@register.inclusion_tag("core/includes/partners_section.html", takes_context=True)
def render_partners_section(context):
    request = context.get("request")

    partners = (
        Partner.objects
        .filter(is_active=True)
        .select_related("logo")
        .order_by("sort_order", "name", "id")
    )

    return {
        "request": request,
        "partners": partners,
    }