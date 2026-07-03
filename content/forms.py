from django import forms
from django.utils.text import slugify

from events.models import Event
from media_assets.models import MediaAsset

from .models import ContentPost


class ContentPostForm(forms.ModelForm):
    class Meta:
        model = ContentPost
        fields = [
            "title",
            "slug",
            "event",
            "cover_image",
            "author_name",
            "perex",
            "keywords",
            "is_published",
            "published_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "event": forms.Select(attrs={"class": "form-control"}),
            "cover_image": forms.Select(attrs={"class": "form-control"}),
            "author_name": forms.TextInput(attrs={"class": "form-control"}),
            "perex": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "keywords": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "published_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["slug"].required = False
        self.fields["event"].required = False
        self.fields["cover_image"].required = False
        self.fields["published_at"].required = False

        self.fields["event"].queryset = Event.objects.all().order_by("-starts_at")
        self.fields["cover_image"].queryset = MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at")

        self.fields["event"].empty_label = "— bez navázaného koncertu —"
        self.fields["cover_image"].empty_label = "— bez úvodního obrázku —"

        self.fields["published_at"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_slug(self):
        slug = self.cleaned_data.get("slug")
        title = self.cleaned_data.get("title")

        if not slug and title:
            slug = slugify(title)

        if not slug:
            raise forms.ValidationError("Slug se nepodařilo vygenerovat.")

        qs = ContentPost.objects.filter(slug=slug)

        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError("Tento slug už existuje. Zvol jiný.")

        return slug