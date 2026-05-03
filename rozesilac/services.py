from .models import ContactGroup, WEB_CONTACT_GROUP_CODE, WEB_CONTACT_GROUP_NAME


def get_web_contacts_group():
    group = ContactGroup.objects.filter(system_code=WEB_CONTACT_GROUP_CODE).first()

    if group:
        changed = False

        if not group.is_protected:
            group.is_protected = True
            changed = True

        if not group.name:
            group.name = WEB_CONTACT_GROUP_NAME
            changed = True

        if changed:
            group.save(update_fields=["name", "is_protected"])

        return group

    group, created = ContactGroup.objects.get_or_create(
        name=WEB_CONTACT_GROUP_NAME,
        defaults={
            "system_code": WEB_CONTACT_GROUP_CODE,
            "is_protected": True,
        },
    )

    if not group.system_code or not group.is_protected:
        group.system_code = WEB_CONTACT_GROUP_CODE
        group.is_protected = True
        group.save(update_fields=["system_code", "is_protected"])

    return group