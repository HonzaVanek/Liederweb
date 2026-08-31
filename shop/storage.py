from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateShopStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "location",
            settings.SHOP_PRIVATE_MEDIA_ROOT,
        )
        super().__init__(*args, **kwargs)

    def url(self, name):
        """
        Privátní soubory nikdy nemají veřejnou /media/ URL.

        URL vede pouze přes staff-only Django view.
        """
        return reverse(
            "shop_staff:private_file",
            kwargs={"path": name},
        )


private_shop_storage = PrivateShopStorage()