from rozesilac.models import Contact, ContactGroup


SHOP_CONTACT_GROUP_CODE = "shop"
SHOP_CONTACT_GROUP_NAME = "Kontakty z e-shopu"


def get_shop_contacts_group():
    group = ContactGroup.objects.filter(
        system_code=SHOP_CONTACT_GROUP_CODE,
    ).first()

    if group:
        changed = False

        if not group.is_protected:
            group.is_protected = True
            changed = True

        if not group.name:
            group.name = SHOP_CONTACT_GROUP_NAME
            changed = True

        if changed:
            group.save(
                update_fields=["name", "is_protected"]
            )

        return group

    group, created = ContactGroup.objects.get_or_create(
        name=SHOP_CONTACT_GROUP_NAME,
        defaults={
            "system_code": SHOP_CONTACT_GROUP_CODE,
            "is_protected": True,
        },
    )

    if not group.system_code or not group.is_protected:
        group.system_code = SHOP_CONTACT_GROUP_CODE
        group.is_protected = True
        group.save(
            update_fields=["system_code", "is_protected"]
        )

    return group


def add_order_contact_to_newsletter(order):
    if not order.newsletter_consent:
        return

    email = order.email.strip().lower()
    name = order.customer_name.strip()

    contact, created = Contact.objects.get_or_create(
        email=email,
        defaults={
            "name": name,
            "is_active": True,
        },
    )

    update_fields = []

    if not contact.is_active:
        contact.is_active = True
        update_fields.append("is_active")

    if name and not contact.name:
        contact.name = name
        update_fields.append("name")

    if update_fields:
        contact.save(update_fields=update_fields)

    contact.groups.add(get_shop_contacts_group())