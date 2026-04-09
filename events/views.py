from django.shortcuts import render, redirect, get_object_or_404

from core.decorators import staff_required

from .models import Event
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
        "page_title": "Nový koncert",
    })


@staff_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)

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
        "event": event,
    })


@staff_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)

    return render(request, "events/event_detail.html", {
        "event": event,
    })