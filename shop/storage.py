from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateShopStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "location",
            settings.SHOP_PRIVATE_MEDIA_ROOT,
        )
        kwargs.setdefault(
            "base_url",
            None,
        )

        super().__init__(*args, **kwargs)


private_shop_storage = PrivateShopStorage()