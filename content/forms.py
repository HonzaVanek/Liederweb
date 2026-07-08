from django import forms
from django.utils.text import slugify

from events.models import Event
from media_assets.models import MediaAsset

from .models import ContentBlock, ContentBlockImage, ContentPost, ContentGallery, ContentGalleryImage


class ContentPostForm(forms.ModelForm):
    class Meta:
        model = ContentPost
        fields = [
            "title",
            "slug",
            "event",
            "cover_image",
            "cover_image_position",
            "cover_image_fit",
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
            "cover_image_fit": forms.Select(attrs={"class": "form-control"}),
            "cover_image_position": forms.Select(attrs={"class": "form-control"}),
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
    
class ContentBlockForm(forms.ModelForm):
    class Meta:
        model = ContentBlock
        fields = [
            "text",
            "youtube_url",
            "button_label",
            "button_url",
            "button_color",
        ]
        widgets = {
            "text": forms.Textarea(attrs={"class": "form-control content-richtext-textarea", "rows": 12, "data-content-richtext": "1"}),
            "youtube_url": forms.URLInput(attrs={"class": "form-control"}),
            "button_label": forms.TextInput(attrs={"class": "form-control"}),
            "button_url": forms.URLInput(attrs={"class": "form-control"}),
            "button_color": forms.TextInput(attrs={"class": "form-control content-color-input", "type": "color"}),
        }

    def __init__(self, *args, **kwargs):
        self.block_type = kwargs.pop("block_type", None)

        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.block_type = self.block_type or self.instance.block_type

        if self.block_type == ContentBlock.BLOCK_TEXT:
            self.fields["text"].help_text = (
                "Sem normálně nakopíruj jeden nebo více odstavců textu článku. "
                "Chceš-li nějaké základní formátování, označ text který chceš mít jinak a použij tlačítka nad polem: tučně vloží **text**, "
                "kurzíva vloží *text*, odrážka přidá '- ' na začátek řádku. "
                "Tlačítko pevná mezera vloží &nbsp; na místo kurzoru. "
                "Prázdný řádek vytvoří nový odstavec, běžný Enter vytvoří nový řádek."
            )
            self.fields = {
                "text": self.fields["text"],
            }

        elif self.block_type == ContentBlock.BLOCK_YOUTUBE:
            self.fields = {
                "youtube_url": self.fields["youtube_url"],
            }

        elif self.block_type == ContentBlock.BLOCK_CTA:
            self.fields["button_color"].help_text = (
                "Vyber barvu tlačítka. Barva textu se na veřejné stránce dopočítá automaticky podle kontrastu."
            )

            self.fields = {
                "button_label": self.fields["button_label"],
                "button_url": self.fields["button_url"],
                "button_color": self.fields["button_color"],
            }

        elif self.block_type == ContentBlock.BLOCK_GALLERY:
            self.fields = {}

    def clean_button_color(self):
        color = self.cleaned_data.get("button_color") or "#111111"
        return color.lower()

    def clean(self):
        cleaned_data = super().clean()

        if self.block_type == ContentBlock.BLOCK_TEXT:
            text = cleaned_data.get("text", "").strip()
            if not text:
                self.add_error("text", "Textový blok nesmí být prázdný.")

        elif self.block_type == ContentBlock.BLOCK_YOUTUBE:
            youtube_url = cleaned_data.get("youtube_url", "").strip()
            if not youtube_url:
                self.add_error("youtube_url", "Zadej URL YouTube videa.")

        elif self.block_type == ContentBlock.BLOCK_CTA:
            button_label = cleaned_data.get("button_label", "").strip()
            button_url = cleaned_data.get("button_url", "").strip()

            if not button_label:
                self.add_error("button_label", "Zadej text tlačítka.")

            if not button_url:
                self.add_error("button_url", "Zadej URL tlačítka.")

        return cleaned_data


class ContentBlockImageForm(forms.ModelForm):
    class Meta:
        model = ContentBlockImage
        fields = [
            "image",
            "image_fit",
            "image_position",
            "caption",
            "alt_text",
        ]
        widgets = {
            "image": forms.Select(attrs={"class": "form-control"}),
            "image_fit": forms.Select(attrs={"class": "form-control"}),
            "image_position": forms.Select(attrs={"class": "form-control"}),
            "caption": forms.TextInput(attrs={"class": "form-control"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["image"].queryset = MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at")

        self.fields["image"].empty_label = "— vyber obrázek —"


class ContentGalleryForm(forms.ModelForm):
    class Meta:
        model = ContentGallery
        fields = [
            "title",
            "slug",
            "event",
            "cover_image",
            "cover_image_fit",
            "cover_image_position",
            "description",
            "is_published",
            "published_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "event": forms.Select(attrs={"class": "form-control"}),
            "cover_image": forms.Select(attrs={"class": "form-control"}),
            "cover_image_fit": forms.Select(attrs={"class": "form-control"}),
            "cover_image_position": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "published_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }
        input_formats = {
            "published_at": ["%Y-%m-%dT%H:%M"],
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["slug"].required = False

        self.fields["event"].queryset = Event.objects.all().order_by("-starts_at")
        self.fields["event"].empty_label = "— bez navázaného koncertu —"

        self.fields["cover_image"].queryset = MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at")
        self.fields["cover_image"].empty_label = "— bez úvodního obrázku —"

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()

        if not slug:
            title = self.cleaned_data.get("title") or ""
            slug = slugify(title)

        if not slug:
            raise forms.ValidationError("Slug se nepodařilo vytvořit. Vyplň název nebo slug ručně.")

        queryset = ContentGallery.objects.filter(slug=slug)

        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise forms.ValidationError("Galerie s tímto slugem už existuje.")

        return slug
    

class ContentGalleryImageForm(forms.ModelForm):
    class Meta:
        model = ContentGalleryImage
        fields = [
            "image",
            "caption",
            "alt_text",
            "image_fit",
            "image_position",
        ]
        widgets = {
            "image": forms.Select(attrs={"class": "form-control"}),
            "caption": forms.TextInput(attrs={"class": "form-control"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control"}),
            "image_fit": forms.Select(attrs={"class": "form-control"}),
            "image_position": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["image"].queryset = MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at")

        self.fields["image"].empty_label = "— vyber obrázek —"