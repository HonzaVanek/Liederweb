from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import MediaAsset

from pathlib import Path


MEDIA_ASSETS_TOTAL_LIMIT = 750 * 1024 * 1024  # 750 MB


class MediaAssetForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = [
            "title",
            "file",
            "alt_text",
            "description",
            "credit",
            "is_active",
        ]

    def clean(self):
        cleaned_data = super().clean()

        uploaded_file = self.files.get("file")
        if not uploaded_file:
            return cleaned_data

        current_total = MediaAsset.objects.aggregate(total=Sum("file_size"))["total"] or 0

        # Při editaci a výměně souboru odečteme starou velikost
        if self.instance and self.instance.pk:
            current_total -= self.instance.file_size or 0

        if current_total + uploaded_file.size > MEDIA_ASSETS_TOTAL_LIMIT:
            raise ValidationError(
                "Nelze nahrát další soubor. Mediální knihovna by překročila limit 750 MB. "
                "Nejdřív je potřeba smazat pár nepoužívaných assetů."
            )

        return cleaned_data
    

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_file_clean = super().clean

        if isinstance(data, (list, tuple)):
            return [single_file_clean(file, initial) for file in data]

        return [single_file_clean(data, initial)]


class MediaAssetBulkImageUploadForm(forms.Form):
    files = MultipleFileField(
        label="Fotky",
        widget=MultipleFileInput(
            attrs={
                "multiple": True,
                "accept": "image/*",
            }
        ),
        help_text="Vyber jednu nebo více fotek. Každá fotka se uloží jako samostatný asset.",
    )

    credit = forms.CharField(
        label="Společný kredit",
        required=False,
        max_length=255,
        help_text="Volitelné. Použije se u všech nahraných fotek.",
    )

    description = forms.CharField(
        label="Společný popis",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Volitelné. Použije se u všech nahraných fotek.",
    )

    is_active = forms.BooleanField(
        label="Aktivní",
        required=False,
        initial=True,
        help_text="Neaktivní assety se nemají používat ve veřejné části webu.",
    )

    def clean_files(self):
        files = self.cleaned_data["files"]

        if not files:
            raise ValidationError("Vyber alespoň jeden soubor.")

        if len(files) > 50:
            raise ValidationError("Najednou lze nahrát maximálně 50 fotek.")

        for uploaded_file in files:
            content_type = uploaded_file.content_type or ""

            if not content_type.startswith("image/"):
                raise ValidationError(
                    f"Soubor „{uploaded_file.name}“ není obrázek."
                )

        return files