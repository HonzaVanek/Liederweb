from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import MediaAsset


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