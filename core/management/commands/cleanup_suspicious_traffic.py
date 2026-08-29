import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import models

from core.models import (
    DailyEngagedVisitor,
    DailySiteVisitor,
    TrafficVisitCandidate,
    DailyBrowserVisitor,
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


def find_repeated_two_step_sequences(
    rows,
    *,
    max_step_seconds=2.5,
    min_session_gap_seconds=300,
):
    rows = sorted(
        rows,
        key=lambda row: row.created_at,
    )

    sequences = defaultdict(list)

    for first, second in zip(rows, rows[1:]):
        gap = (
            second.created_at
            - first.created_at
        ).total_seconds()

        if gap < 0 or gap > max_step_seconds:
            continue

        if first.path == second.path:
            continue

        sequences[
            (
                first.path,
                second.path,
            )
        ].append(
            (
                first,
                second,
            )
        )

    flagged = set()

    for occurrences in sequences.values():
        if len(occurrences) < 2:
            continue

        # Nestačí dvě překrývající se dvojice v jednom burstu.
        first_occurrence = occurrences[0]

        for occurrence in occurrences[1:]:
            session_gap = (
                occurrence[0].created_at
                - first_occurrence[0].created_at
            ).total_seconds()

            if session_gap < min_session_gap_seconds:
                continue

            flagged.update({
                first_occurrence[0].pk,
                first_occurrence[1].pk,
                occurrence[0].pk,
                occurrence[1].pk,
            })

    return flagged


def find_distributed_multi_path_sweeps(
    rows,
    *,
    seconds,
    min_clients,
    min_paths,
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

        unique_clients = {
            row.client_hash
            for row in window
        }

        unique_paths = {
            row.path
            for row in window
            if row.path
        }

        if (
            len(unique_clients) >= min_clients
            and len(unique_paths) >= min_paths
        ):
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

        context_candidates = list(
            TrafficVisitCandidate.objects
            .filter(
                day__in=days,
                created_at__gte=now - timedelta(days=14),
            )
            .filter(
                models.Q(
                    decision=TrafficVisitCandidate.Decision.PENDING,
                    created_at__lte=evaluation_cutoff,
                )
                |
                models.Q(
                    decision=TrafficVisitCandidate.Decision.KEPT,
                    decision_reason="no_posthoc_rule_matched",
                )
            )
            .order_by("created_at")
        )


        browser_keys = set()
        engaged_keys = set()
        existing_visitor_keys = set()

        for day in days:
            hashes = {
                candidate.visitor_hash
                for candidate in context_candidates
                if candidate.day == day
            }

            browser_keys.update(
                (day, visitor_hash)
                for visitor_hash in (
                    DailyBrowserVisitor.objects
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


            confirmed_keys = browser_keys | engaged_keys

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

        browser_only_ids = [
            candidate.pk
            for candidate in candidates
            if (
                candidate.day,
                candidate.visitor_hash,
            ) in browser_keys
            and (
                candidate.day,
                candidate.visitor_hash,
            ) not in engaged_keys
        ]

        if engaged_ids:
            TrafficVisitCandidate.objects.filter(
                pk__in=engaged_ids
            ).update(
                decision=TrafficVisitCandidate.Decision.KEPT,
                decision_reason="engaged",
                processed_at=now,
            )

        if browser_only_ids:
            TrafficVisitCandidate.objects.filter(
                pk__in=browser_only_ids
            ).update(
                decision=TrafficVisitCandidate.Decision.KEPT,
                decision_reason="browser_confirmed",
                processed_at=now,
            )

        working = [
            candidate
            for candidate in candidates
            if candidate.pk not in already_removed_ids
            and (
                candidate.day,
                candidate.visitor_hash,
            ) not in confirmed_keys
        ]

        context_working = [
            candidate
            for candidate in context_candidates
            if (
                candidate.day,
                candidate.visitor_hash,
            ) in existing_visitor_keys
            and (
                candidate.day,
                candidate.visitor_hash,
            ) not in confirmed_keys
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
        # RULE 1B:
        # stejný UA + path + EMPTY referer
        # z >= 3 různých clientů během 15 sekund
        # -------------------------------------------------

        empty_groups = defaultdict(list)

        for candidate in working:
            if candidate.is_social_iab:
                continue

            if (
                candidate.referer_kind
                != TrafficVisitCandidate.RefererKind.EMPTY
            ):
                continue

            empty_groups[
                (
                    candidate.day,
                    candidate.path,
                    candidate.user_agent_hash,
                )
            ].append(candidate)

        for rows in empty_groups.values():
            ids = find_distinct_client_bursts(
                rows,
                seconds=15,
                min_clients=3,
            )

            for candidate_id in ids:
                reasons_by_candidate.setdefault(
                    candidate_id,
                    "distributed_same_ua_empty_ref_no_engagement",
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

        # -------------------------------------------------
        # RULE 3:
        # stejný visitor opakovaně provede stejnou
        # dvoukrokovou sekvenci velmi rychle,
        # bez engagementu
        # -------------------------------------------------

        sequence_groups = defaultdict(list)

        for candidate in context_working:
            if candidate.is_social_iab:
                continue

            if candidate.referer_kind not in (
                TrafficVisitCandidate.RefererKind.EMPTY,
                TrafficVisitCandidate.RefererKind.OWN,
            ):
                continue

            sequence_groups[
                (
                    candidate.day,
                    candidate.visitor_hash,
                    candidate.user_agent_hash,
                    candidate.referer_kind,
                    candidate.referer_host,
                )
            ].append(candidate)

        for rows in sequence_groups.values():
            ids = find_repeated_two_step_sequences(
                rows,
                max_step_seconds=2.5,
                min_session_gap_seconds=300,
            )

            for candidate_id in ids:
                reasons_by_candidate.setdefault(
                    candidate_id,
                    "repeated_two_step_sequence_no_engagement",
                )

        # -------------------------------------------------
        # RULE 4:
        # stejný přesný UA se bez refereru rozlézá
        # z mnoha různých clientů přes mnoho různých stránek
        #
        # Dlouhé okno je záměrné — typický distribuovaný
        # scanner může pracovat celé hodiny.
        # -------------------------------------------------

        distributed_ua_groups = defaultdict(list)

        for candidate in context_working:
            if candidate.is_social_iab:
                continue

            if (
                candidate.referer_kind
                != TrafficVisitCandidate.RefererKind.EMPTY
            ):
                continue

            distributed_ua_groups[
                (
                    candidate.day,
                    candidate.user_agent_hash,
                )
            ].append(candidate)

        for rows in distributed_ua_groups.values():
            ids = find_distributed_multi_path_sweeps(
                rows,
                seconds=6 * 60 * 60,
                min_clients=8,
                min_paths=5,
            )

            for candidate_id in ids:
                reasons_by_candidate.setdefault(
                    candidate_id,
                    "distributed_same_ua_multi_path_no_engagement",
                )


        suspicious_candidates = [
            candidate
            for candidate in context_working
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
            is_confirmed = (
                DailyBrowserVisitor.objects.filter(
                    day=day,
                    visitor_hash=visitor_hash,
                ).exists()
                or
                DailyEngagedVisitor.objects.filter(
                    day=day,
                    visitor_hash=visitor_hash,
                ).exists()
            )

            if is_confirmed:
                TrafficVisitCandidate.objects.filter(
                    day=day,
                    visitor_hash=visitor_hash,
                    decision=TrafficVisitCandidate.Decision.PENDING,
                ).update(
                    decision=TrafficVisitCandidate.Decision.KEPT,
                    decision_reason="js_confirmed_before_cleanup",
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
                ).filter(
                    models.Q(
                        decision=TrafficVisitCandidate.Decision.PENDING,
                    )
                    |
                    models.Q(
                        decision=TrafficVisitCandidate.Decision.KEPT,
                        decision_reason="no_posthoc_rule_matched",
                    )
                ).update(
                    decision=TrafficVisitCandidate.Decision.CLEANED,
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