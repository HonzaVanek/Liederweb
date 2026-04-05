from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from rozesilac.models import EmailCampaign
from rozesilac.views import send_campaign_deliveries


class Command(BaseCommand):
    help = "Odešle naplánované emailové kampaně, jejichž čas už nastal."

    def handle(self, *args, **options):
        now = timezone.now()

        campaign_ids = list(
            EmailCampaign.objects.filter(
                status="scheduled",
                is_test=False,
                scheduled_at__isnull=False,
                scheduled_at__lte=now,
            ).values_list("id", flat=True)
        )

        if not campaign_ids:
            self.stdout.write(self.style.SUCCESS("Žádné kampaně k odeslání."))
            return

        self.stdout.write(f"Nalezeno kampaní k odeslání: {len(campaign_ids)}")

        for campaign_id in campaign_ids:
            try:
                with transaction.atomic():
                    campaign = (
                        EmailCampaign.objects.select_for_update()
                        .select_related("created_by", "template")
                        .get(id=campaign_id)
                    )

                    # druhá kontrola uvnitř transakce:
                    # aby se kampaň neposlala dvakrát
                    if campaign.status != "scheduled":
                        self.stdout.write(
                            f"Kampaň #{campaign.id} přeskočena: status je {campaign.status}."
                        )
                        continue

                    if not campaign.scheduled_at or campaign.scheduled_at > timezone.now():
                        self.stdout.write(
                            f"Kampaň #{campaign.id} přeskočena: čas ještě nenastal."
                        )
                        continue

                    self.stdout.write(
                        f"Spouštím kampaň #{campaign.id}: {campaign.subject}"
                    )

                # mimo transaction:
                # samotné odesílání může trvat dlouho, nechceme držet DB lock
                base_url = getattr(settings, "NEWSLETTER_BASE_URL", "").strip()
                if not base_url:
                    raise Exception(
                        "V settings chybí NEWSLETTER_BASE_URL, bez ní nelze generovat absolutní odkazy."
                    )

                from_email = (
                        campaign.from_email
                        or getattr(settings, "NEWSLETTER_DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL)
                    )

                sent_count, failed_count = send_campaign_deliveries(
                    campaign=campaign,
                    base_url=base_url.rstrip("/"),
                    from_email=from_email,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Kampaň #{campaign.id} dokončena. Odesláno: {sent_count}, chyb: {failed_count}."
                    )
                )

            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"Kampaň #{campaign_id} selhala: {exc}"
                    )
                )

                try:
                    campaign = EmailCampaign.objects.get(id=campaign_id)
                    campaign.status = "failed"
                    campaign.finished_at = timezone.now()
                    campaign.save(update_fields=["status", "finished_at"])
                except Exception:
                    pass