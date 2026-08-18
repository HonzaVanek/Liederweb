import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    DailyEngagedVisitor,
    DailySiteVisitor,
    TrafficVisitCandidate,
)
from core.traffic_cleanup import (
    cleanup_visitor_human_stats,
)


logger = logging.getLogger("liederweb.traffic")


def find_distinct_client_bursts(
    rows,
    *,
    seconds,
    min_clients,
):
    rows = sorted(
        rows,
        key=lambda row: row.created_at,
    )

    flagged = set()
    left = 0

    for right, current in enumerate(rows):
        while (
            left < right
            and (
                current.created_at
                - rows[left].created_at
            ).total_seconds() > seconds
        ):
            left += 1

        window = rows[left:right + 1]

        if len({
            row.client_hash
            for row in window
        }) >= min_clients:
            flagged.update(
                row.pk
                for row in window
            )

    return flagged


def find_repeated_event_bursts(
    rows,
    *,
    seconds,
    min_events,
):
    rows = sorted(
        rows,
        key=lambda row: row.created_at,
    )

    flagged = set()
    left = 0

    for right, current in enumerate(rows):
        while (
            left < right
            and (
                current.created_at
                - rows[left].created_at
            ).total_seconds() > seconds
        ):
            left += 1

        window = rows[left:right + 1]

        if len(window) >= min_events:
            flagged.update(
                row.pk
                for row in window
            )

    return flagged


class Command(BaseCommand):
    help = (
        "Zpětně vyhodnotí nepotvrzené traffic VISIT "
        "a odstraní silně bot-like patterny."
    )

    def handle(self, *args, **options):
        now = timezone.now()

        # Kandidát musí mít nejméně 10 minut na případný beacon.
        evaluation_cutoff = now - timedelta(minutes=10)

        # Definitivně ho uzavřeme až o další minutu později,
        # protože nejdelší post-hoc pattern používá 60s okno.
        finalize_cutoff = (
            evaluation_cutoff
            - timedelta(seconds=60)
        )

        candidates = list(
            TrafficVisitCandidate.objects
            .filter(
                decision=TrafficVisitCandidate.Decision.PENDING,
                created_at__lte=evaluation_cutoff,
                created_at__gte=now - timedelta(days=14),
            )
            .order_by("created_at")[:10000]
        )

        if not candidates:
            self.cleanup_old_candidates(now)
            self.stdout.write("No candidates.")
            return

        days = {
            candidate.day
            for candidate in candidates
        }

        engaged_keys = set()
        existing_visitor_keys = set()

        for day in days:
            hashes = {
                candidate.visitor_hash
                for candidate in candidates
                if candidate.day == day
            }

            engaged_keys.update(
                (day, visitor_hash)
                for visitor_hash in (
                    DailyEngagedVisitor.objects
                    .filter(
                        day=day,
                        visitor_hash__in=hashes,
                    )
                    .values_list(
                        "visitor_hash",
                        flat=True,
                    )
                )
            )

            existing_visitor_keys.update(
                (day, visitor_hash)
                for visitor_hash in (
                    DailySiteVisitor.objects
                    .filter(
                        day=day,
                        visitor_hash__in=hashes,
                    )
                    .values_list(
                        "visitor_hash",
                        flat=True,
                    )
                )
            )

        # Visitor mohl být mezitím odstraněn realtime MW.
        already_removed_ids = [
            candidate.pk
            for candidate in candidates
            if (
                candidate.day,
                candidate.visitor_hash,
            ) not in existing_visitor_keys
        ]

        if already_removed_ids:
            TrafficVisitCandidate.objects.filter(
                pk__in=already_removed_ids
            ).update(
                decision=(
                    TrafficVisitCandidate
                    .Decision.ALREADY_REMOVED
                ),
                decision_reason="realtime_cleanup",
                processed_at=now,
            )

        engaged_ids = [
            candidate.pk
            for candidate in candidates
            if (
                candidate.day,
                candidate.visitor_hash,
            ) in engaged_keys
        ]

        if engaged_ids:
            TrafficVisitCandidate.objects.filter(
                pk__in=engaged_ids
            ).update(
                decision=TrafficVisitCandidate.Decision.KEPT,
                decision_reason="engaged",
                processed_at=now,
            )

        working = [
            candidate
            for candidate in candidates
            if candidate.pk not in already_removed_ids
            and candidate.pk not in engaged_ids
        ]

        reasons_by_candidate = {}

        # -------------------------------------------------
        # RULE 1:
        # stejný UA + path + own referer
        # z >= 3 různých clientů během 15 sekund
        # -------------------------------------------------

        own_groups = defaultdict(list)

        for candidate in working:
            if candidate.is_social_iab:
                continue

            if (
                candidate.referer_kind
                != TrafficVisitCandidate.RefererKind.OWN
            ):
                continue

            own_groups[
                (
                    candidate.day,
                    candidate.path,
                    candidate.user_agent_hash,
                )
            ].append(candidate)

        for rows in own_groups.values():
            ids = find_distinct_client_bursts(
                rows,
                seconds=15,
                min_clients=3,
            )

            for candidate_id in ids:
                reasons_by_candidate.setdefault(
                    candidate_id,
                    "distributed_same_ua_own_ref_no_engagement",
                )

        # -------------------------------------------------
        # RULE 2:
        # jeden visitor opakovaně otevírá stejnou stránku,
        # bez beaconu, bez search/external refereru
        # -------------------------------------------------

        repeated_groups = defaultdict(list)

        for candidate in working:
            if candidate.is_social_iab:
                continue

            if candidate.referer_kind not in (
                TrafficVisitCandidate.RefererKind.EMPTY,
                TrafficVisitCandidate.RefererKind.OWN,
            ):
                continue

            repeated_groups[
                (
                    candidate.day,
                    candidate.visitor_hash,
                    candidate.path,
                )
            ].append(candidate)

        for rows in repeated_groups.values():
            ids = find_repeated_event_bursts(
                rows,
                seconds=60,
                min_events=3,
            )

            for candidate_id in ids:
                reasons_by_candidate.setdefault(
                    candidate_id,
                    "repeated_visit_no_engagement",
                )

        suspicious_candidates = [
            candidate
            for candidate in working
            if candidate.pk in reasons_by_candidate
        ]

        suspicious_visitors = defaultdict(list)

        for candidate in suspicious_candidates:
            suspicious_visitors[
                (
                    candidate.day,
                    candidate.visitor_hash,
                )
            ].append(candidate)

        cleaned_visitors = 0
        cleaned_pageviews = 0

        for (
            day,
            visitor_hash,
        ), rows in suspicious_visitors.items():

            # Poslední pojistka těsně před cleanupem.
            if DailyEngagedVisitor.objects.filter(
                day=day,
                visitor_hash=visitor_hash,
            ).exists():
                TrafficVisitCandidate.objects.filter(
                    day=day,
                    visitor_hash=visitor_hash,
                    decision=(
                        TrafficVisitCandidate
                        .Decision.PENDING
                    ),
                ).update(
                    decision=TrafficVisitCandidate.Decision.KEPT,
                    decision_reason="engaged_before_cleanup",
                    processed_at=now,
                )
                continue

            reasons = sorted({
                reasons_by_candidate[row.pk]
                for row in rows
            })

            reason = "+".join(reasons)

            removed = cleanup_visitor_human_stats(
                day,
                visitor_hash,
                delete_engaged=False,
            )

            if removed:
                cleaned_visitors += 1
                cleaned_pageviews += removed

                TrafficVisitCandidate.objects.filter(
                    day=day,
                    visitor_hash=visitor_hash,
                    decision=(
                        TrafficVisitCandidate
                        .Decision.PENDING
                    ),
                ).update(
                    decision=(
                        TrafficVisitCandidate
                        .Decision.CLEANED
                    ),
                    decision_reason=reason[:160],
                    processed_at=now,
                )

                sample = rows[0]

                logger.info(
                    "POSTHOC_CLEANUP "
                    "client=%s visitor=%s "
                    "path=%s reason=%s "
                    "removed_pageviews=%s candidates=%s",
                    sample.client_hash[:8],
                    visitor_hash[:8],
                    sample.path[:300],
                    reason,
                    removed,
                    len(rows),
                )

        # Co nebylo podezřelé, definitivně uzavřeme až po ochranném
        # přesahu 60 sekund, aby se pattern nerozsekl hranicí cronu.
        TrafficVisitCandidate.objects.filter(
            pk__in=[
                candidate.pk
                for candidate in working
                if (
                    candidate.pk not in reasons_by_candidate
                    and candidate.created_at <= finalize_cutoff
                )
            ],
            decision=TrafficVisitCandidate.Decision.PENDING,
        ).update(
            decision=TrafficVisitCandidate.Decision.KEPT,
            decision_reason="no_posthoc_rule_matched",
            processed_at=now,
        )

        self.cleanup_old_candidates(now)

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed={len(candidates)}, "
                f"cleaned_visitors={cleaned_visitors}, "
                f"cleaned_pageviews={cleaned_pageviews}"
            )
        )

    def cleanup_old_candidates(self, now):
        TrafficVisitCandidate.objects.filter(
            created_at__lt=now - timedelta(days=14)
        ).delete()