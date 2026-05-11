from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from rozesilac.models import EmailCampaign
from rozesilac.views import send_campaign_deliveries
from rozesilac.email_limits import can_fit_email_count_in_day


class Command(BaseCommand):
    help = "Odešle naplánované emailové kampaně, jejichž čas už nastal."

    def handle(self, *args, **options):
        base_url = getattr(settings, "NEWSLETTER_BASE_URL", "").strip().rstrip("/")

        if not base_url:
            self.stderr.write(
                self.style.ERROR(
                    "V settings chybí NEWSLETTER_BASE_URL, bez ní nelze generovat absolutní odkazy."
                )
            )
            return

        # --------------------------------------------------
        # Pokud už se něco odesílá, cron nespouští další kampaň.
        # Chrání to denní limit i souběh scheduled vs manual send.
        # --------------------------------------------------

        running_campaign = (
            EmailCampaign.objects
            .filter(status="sending")
            .order_by("-started_at", "-id")
            .first()
        )

        if running_campaign:
            started_at_text = (
                timezone.localtime(running_campaign.started_at).strftime("%d.%m.%Y %H:%M")
                if running_campaign.started_at
                else "neznámý čas"
            )

            self.stdout.write(
                f"Cron nic nespustil: právě se odesílá kampaň "
                f"#{running_campaign.id} od {started_at_text}."
            )
            return

        now = timezone.now()

        campaign_ids = list(
            EmailCampaign.objects.filter(
                status="scheduled",
                is_test=False,
                scheduled_at__isnull=False,
                scheduled_at__lte=now,
            )
            .order_by("scheduled_at", "id")
            .values_list("id", flat=True)
        )

        if not campaign_ids:
            return

        self.stdout.write(f"Nalezeno kampaní k odeslání: {len(campaign_ids)}")

        for campaign_id in campaign_ids:
            try:
                # --------------------------------------------------
                # Před každou kampaní znovu ověříme, že mezitím
                # nezačala běžet jiná rozesílka.
                # --------------------------------------------------

                running_campaign = (
                    EmailCampaign.objects
                    .filter(status="sending")
                    .order_by("-started_at", "-id")
                    .first()
                )

                if running_campaign:
                    self.stdout.write(
                        f"Další scheduled kampaně se teď nespustí, protože právě běží "
                        f"kampaň #{running_campaign.id}."
                    )
                    return

                claim_now = timezone.now()

                # --------------------------------------------------
                # Atomické převzetí kampaně.
                #
                # Tohle je hlavní ochrana proti tomu, aby stejnou
                # kampaň převzaly dva crony zároveň.
                # --------------------------------------------------

                claimed_count = EmailCampaign.objects.filter(
                    id=campaign_id,
                    status="scheduled",
                    is_test=False,
                    scheduled_at__isnull=False,
                    scheduled_at__lte=claim_now,
                ).update(
                    status="sending",
                    started_at=claim_now,
                    finished_at=None,
                )

                if claimed_count == 0:
                    self.stdout.write(
                        f"Kampaň #{campaign_id} přeskočena: už ji převzal jiný proces, "
                        f"nebo už není naplánovaná."
                    )
                    continue

                campaign = (
                    EmailCampaign.objects
                    .select_related("created_by", "template", "event")
                    .get(id=campaign_id)
                )

                queued_count = campaign.deliveries.filter(status="queued").count()

                if queued_count == 0:
                    campaign.status = "sent"
                    campaign.finished_at = timezone.now()
                    campaign.save(update_fields=["status", "finished_at"])

                    self.stdout.write(
                        f"Kampaň #{campaign.id} nemá žádné queued příjemce. Označeno jako sent."
                    )
                    continue

                # --------------------------------------------------
                # Kontrola denního limitu těsně před scheduled odesláním.
                #
                # exclude_campaign_id je důležité, protože tahle kampaň
                # už je v tuhle chvíli status=sending a jinak by se mohla
                # započítat sama proti sobě jako rezervace.
                # --------------------------------------------------

                capacity_check = can_fit_email_count_in_day(
                    queued_count,
                    day=timezone.now(),
                    exclude_campaign_id=campaign.id,
                )

                if not capacity_check["ok"]:
                    limit_note = (
                        f"Kampaň nebyla odeslána, protože by překročila denní Brevo limit. "
                        f"Limit: {capacity_check['limit']}, "
                        f"odesláno: {capacity_check['sent']}, "
                        f"rezervováno: {capacity_check['reserved']}, "
                        f"zbývá: {capacity_check['remaining']}, "
                        f"kampaň má ve frontě: {queued_count}."
                    )

                    current_note = campaign.note or ""

                    if limit_note not in current_note:
                        campaign.note = ((current_note + " | ") if current_note else "") + limit_note

                    campaign.status = "failed"
                    campaign.finished_at = timezone.now()
                    campaign.save(update_fields=["status", "finished_at", "note"])

                    self.stderr.write(
                        self.style.ERROR(
                            f"Kampaň #{campaign.id} nebyla odeslána: {limit_note}"
                        )
                    )

                    continue

                self.stdout.write(
                    f"Spouštím kampaň #{campaign.id}: {campaign.subject}"
                )

                from_email = (
                    campaign.from_email
                    or getattr(
                        settings,
                        "NEWSLETTER_DEFAULT_FROM_EMAIL",
                        settings.DEFAULT_FROM_EMAIL,
                    )
                )

                sent_count, failed_count = send_campaign_deliveries(
                    campaign=campaign,
                    base_url=base_url,
                    from_email=from_email,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Kampaň #{campaign.id} dokončena. "
                        f"Odesláno: {sent_count}, chyb: {failed_count}."
                    )
                )

            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"Kampaň #{campaign_id} selhala: {exc}"
                    )
                )

                try:
                    EmailCampaign.objects.filter(
                        id=campaign_id,
                        status="sending",
                    ).update(
                        status="failed",
                        finished_at=timezone.now(),
                    )
                except Exception:
                    pass