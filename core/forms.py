from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from media_assets.models import MediaAsset
from .models import Person

class VlastniLoginForm(AuthenticationForm):
    username = forms.CharField(label="Uživatelské jméno")
    password = forms.CharField(label="Heslo", widget=forms.PasswordInput)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            try:
                user = User.objects.get(username=username)
                if not user.check_password(password):
                    raise forms.ValidationError("Zadané heslo není správné.")
            except User.DoesNotExist:
                raise forms.ValidationError("Uživatel s tímto jménem neexistuje.")

        return super().clean()
    

class RegistraceForm(UserCreationForm):
    username = forms.CharField(label="Uživatelské jméno", widget=forms.TextInput(attrs={"placeholder": " "}))
    email = forms.EmailField(required=True, label='Email', widget=forms.EmailInput(attrs={"placeholder": " "}))
    password1 = forms.CharField(label="Heslo", widget=forms.PasswordInput(attrs={"placeholder": " "}))
    password2 = forms.CharField(label="Potvrzení hesla", widget=forms.PasswordInput(attrs={"placeholder": " "}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class PersonForm(forms.ModelForm):
    photo_asset = forms.ModelChoiceField(
        queryset=MediaAsset.objects.filter(
            asset_type=MediaAsset.AssetType.IMAGE,
            is_active=True,
        ).order_by("-uploaded_at"),
        required=False,
        label="Fotografie z mediální knihovny",
        empty_label="— Bez fotografie —",
    )

    class Meta:
        model = Person
        fields = [
            "name",
            "slug",
            "photo_asset",
            "role_short",
            "bio",
            "contact_email",
            "website_url",
            "facebook_url",
            "instagram_url",
            "linkedin_url",
            "x_url",
            "sort_order",
            "is_published",
        ]