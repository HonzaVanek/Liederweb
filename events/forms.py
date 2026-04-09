from django import forms
from .models import Event
from rozesilac.models import EmailImage


class EventForm(forms.ModelForm):
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
            "slug": forms.TextInput(attrs={"placeholder": "za lomítkem v url, např: krasna-magelona"}),
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "venue": forms.TextInput(attrs={"placeholder": "Místo konání"}),
            "public_text": forms.Textarea(attrs={"rows": 6}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["poster_image"].queryset = EmailImage.objects.all().order_by("-uploaded_at")
        self.fields["poster_image"].label = "Plakát koncertu"
        self.fields["poster_image"].help_text = "Vyber obrázek z galerie v sekci Obrázky."