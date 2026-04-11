from django.db import models


class Event(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)

    starts_at = models.DateTimeField(null=True, blank=True)
    venue = models.CharField(max_length=255, blank=True)

    public_text = models.TextField(blank=True)
    poster_image = models.ForeignKey(
        "rozesilac.EmailImage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_posters",
        verbose_name="Plakát koncertu",
    )

    vip_enabled = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class VipReservation(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="vip_reservations")
    contact = models.ForeignKey("rozesilac.Contact", on_delete=models.CASCADE, related_name="vip_reservations")

    campaign = models.ForeignKey(
        "rozesilac.EmailCampaign",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vip_reservations",
    )
    delivery = models.ForeignKey(
        "rozesilac.EmailDelivery",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vip_reservations",
    )
    ticket_count = models.PositiveSmallIntegerField(default=1, verbose_name="Počet vstupenek")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "contact"], name="unique_vip_reservation_per_event_contact")
        ]

    def __str__(self):
        return f"{self.contact.email} – {self.event.title}"