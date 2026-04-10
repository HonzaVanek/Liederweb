from django.shortcuts import render, redirect, get_object_or_404

from core.decorators import staff_required

from .models import Event
from rozesilac.models import EmailImage
from .forms import EventForm


@staff_required
def event_list(request):
    events = Event.objects.order_by("-starts_at", "-created_at")
    return render(request, "events/event_list.html", {"events": events})


@staff_required
def event_create(request):
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm()

    return render(request, "events/event_form.html", {
        "form": form,
        "recent_images": EmailImage.objects.order_by("-uploaded_at")[:8],
        "page_title": "Nový koncert",
    })


@staff_required
def event_edit(request, pk):
    event = get_object_or_404(Event.objects.prefetch_related("campaigns", "vip_reservations"), pk=pk)
    campaigns = event.campaigns.all().order_by("-created_at")
    vip_reservations = event.vip_reservations.all().order_by("-created_at")
    
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            event = form.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm(instance=event)

    return render(request, "events/event_form.html", {
        "form": form,
        "page_title": "Upravit koncert",
        "recent_images": EmailImage.objects.order_by("-uploaded_at")[:8],
        "campaigns": campaigns,
        "vip_reservations": vip_reservations,
        "event": event,
    })


@staff_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)

    return render(request, "events/event_detail.html", {
        "event": event,
    })


def public_event_detail(request, slug):
    event = get_object_or_404(
        Event.objects.select_related("poster_image"),
        slug=slug,
        is_published=True,
    )

    return render(request, "events/public_event_detail.html", {
        "event": event,
        "vip_mode": False,
    })