from django import forms
from django.utils import timezone
from .models import Event
from rozesilac.models import EmailImage


class EventForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "slug",
            "starts_at",
            "venue",
            "public_text",
            "poster_image",
            "vip_enabled",
            "is_published",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Název koncertu"}),
            "slug": forms.TextInput(attrs={"placeholder": "za lomítkem v url, např. krasna-magelona"}),
            "venue": forms.TextInput(attrs={"placeholder": "Místo konání"}),
            "public_text": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["poster_image"].queryset = EmailImage.objects.all().order_by("-uploaded_at")
        self.fields["poster_image"].label = "Plakát koncertu"
        self.fields["poster_image"].required = False

        if self.instance and self.instance.pk and self.instance.starts_at:
            self.initial["starts_at"] = timezone.localtime(
                self.instance.starts_at
            ).strftime("%Y-%m-%dT%H:%M")

    def clean_slug(self):
        slug = self.cleaned_data["slug"].lower()
        reserved = {"create", "edit", "koncerty", "vip", "public", "detail"}

        if slug in reserved:
            raise forms.ValidationError("Tento slug nelze použít.")

        return slug



class VipReservationForm(forms.Form):
    TICKET_COUNT_CHOICES = [
        (1, "1 vstupenka"),
        (2, "2 vstupenky"),
        (3, "3 vstupenky"),
        (4, "4 vstupenky"),
    ]

    ticket_count = forms.TypedChoiceField(
        choices=TICKET_COUNT_CHOICES,
        coerce=int,
        initial=1,
        label="Počet vstupenek",
        widget=forms.RadioSelect,
    )