import logging
import re
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import models
from django.db.models import Count, Exists, Max, Min, OuterRef

from core.models import (
    DailyEngagedVisitor,
    DailyEngagedPageVisitor,
    DailySiteVisitor,
    TrafficVisitCandidate,
    DailyBrowserVisitor,
)
from core.traffic_cleanup import (
    cleanup_visitor_human_stats,
)


logger = logging.getLogger("liederweb.traffic")

# -------------------------------------------------
# Diagnostika distribuovaných crawlerů podle sítě
# -------------------------------------------------

# Díváme se zpětně přes delší období, protože crawler
# může jednotlivé requesty rozprostřít přes několik hodin.
NETWORK_DIAGNOSTIC_WINDOW_HOURS = 12

# Pattern zalogujeme jen tehdy, pokud v něm nedávno
# přibyl nový request. Cron běží po 15 minutách.
NETWORK_DIAGNOSTIC_RECENT_MINUTES = 16

# Zatím pouze diagnostické prahy.
# Nic podle nich nemažeme.
NETWORK_DIAGNOSTIC_MIN_CLIENTS = 3
NETWORK_DIAGNOSTIC_MIN_VISITORS = 3
NETWORK_DIAGNOSTIC_MIN_IPS = 3
NETWORK_DIAGNOSTIC_MIN_PATHS = 3

# Smyslem tohoto pravidla je právě najít crawler,
# který User-Agent rotuje.
NETWORK_DIAGNOSTIC_MIN_UAS = 2


# -------------------------------------------------
# Post-hoc cleanup: distribuovaný no-JS Chrome burst
# -------------------------------------------------

DISTRIBUTED_NO_JS_BURST_SECONDS = 5 * 60

DISTRIBUTED_NO_JS_BURST_MIN_CLIENTS = 8
DISTRIBUTED_NO_JS_BURST_MIN_VISITORS = 8
DISTRIBUTED_NO_JS_BURST_MIN_IPS = 8
DISTRIBUTED_NO_JS_BURST_MIN_PATHS = 6

# Chceme skutečně rotaci browserových verzí,
# ne jen osm lidí se stejným aktuálním Chrome.
DISTRIBUTED_NO_JS_BURST_MIN_CHROME_MAJORS = 4

DESKTOP_CHROME_MAJOR_RE = re.compile(r"\bChrome/(\d+)\.")


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

def get_desktop_chrome_major(user_agent):
    """
    Vrátí major verzi klasického desktop Chrome UA.

    Záměrně sem nepouštíme Edge, Operu, iOS Chrome
    ani HeadlessChrome. Tohle pravidlo má být úzké.
    """
    ua = (user_agent or "").strip()

    if (
        "Windows NT" not in ua
        and "Macintosh" not in ua
    ):
        return None

    if any(
        token in ua
        for token in (
            "Edg/",
            "OPR/",
            "CriOS/",
            "HeadlessChrome/",
        )
    ):
        return None

    match = DESKTOP_CHROME_MAJOR_RE.search(ua)

    if not match:
        return None

    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def find_distributed_no_js_chrome_bursts(
    rows,
    *,
    seconds,
    min_clients,
    min_visitors,
    min_ips,
    min_paths,
    min_chrome_majors,
):
    """
    Najde krátký distribuovaný burst singleton návštěv
    s rotujícími desktop Chrome major verzemi.

    rows už mají být předfiltrované na:
    - EMPTY referer,
    - žádný JS signal,
    - ne social IAB,
    - jeden candidate na visitora i clienta.
    """

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

        clients = {
            row.client_hash
            for row in window
            if row.client_hash
        }

        visitors = {
            row.visitor_hash
            for row in window
            if row.visitor_hash
        }

        ips = {
            row.ip_hash
            for row in window
            if row.ip_hash
        }

        paths = {
            row.path
            for row in window
            if row.path
        }

        chrome_majors = {
            major
            for row in window
            if (
                major := get_desktop_chrome_major(
                    row.user_agent
                )
            ) is not None
        }

        if (
            len(clients) >= min_clients
            and len(visitors) >= min_visitors
            and len(ips) >= min_ips
            and len(paths) >= min_paths
            and len(chrome_majors) >= min_chrome_majors
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

    def log_network_pattern_candidates(self, now):
        """
        Pouze diagnostika.

        Hledá několik nepotvrzených návštěv:

        - ze stejného anonymizovaného networku,
        - z několika různých IP,
        - z několika různých clientů,
        - přes několik různých stránek,
        - bez refereru,
        - bez Browser / Engaged potvrzení,
        - s více různými User-Agenty.

        Nic nemaže a nemění decision.
        Pouze zapíše NETWORK_PATTERN_CANDIDATE do traffic.log.
        """

        window_start = now - timedelta(
            hours=NETWORK_DIAGNOSTIC_WINDOW_HOURS
        )

        recent_start = now - timedelta(
            minutes=NETWORK_DIAGNOSTIC_RECENT_MINUTES
        )

        # Kandidát musí mít stejně jako normální post-hoc
        # cleanup alespoň 10 minut na případný JS beacon.
        mature_cutoff = now - timedelta(minutes=10)

        browser_confirmation = (
            DailyBrowserVisitor.objects
            .filter(
                day=OuterRef("day"),
                visitor_hash=OuterRef("visitor_hash"),
            )
        )

        engaged_confirmation = (
            DailyEngagedVisitor.objects
            .filter(
                day=OuterRef("day"),
                visitor_hash=OuterRef("visitor_hash"),
            )
        )

        candidates = (
            TrafficVisitCandidate.objects
            .filter(
                created_at__gte=window_start,
                created_at__lte=mature_cutoff,
                referer_kind=(
                    TrafficVisitCandidate.RefererKind.EMPTY
                ),
                is_social_iab=False,
            )
            .filter(
                models.Q(
                    decision=(
                        TrafficVisitCandidate.Decision.PENDING
                    ),
                )
                |
                models.Q(
                    decision=(
                        TrafficVisitCandidate.Decision.KEPT
                    ),
                    decision_reason=(
                        "no_posthoc_rule_matched"
                    ),
                )
            )
            .exclude(ip_hash="")
            .exclude(network_hash="")
            .annotate(
                has_browser_confirmation=Exists(
                    browser_confirmation
                ),
                has_engaged_confirmation=Exists(
                    engaged_confirmation
                ),
            )
            .filter(
                has_browser_confirmation=False,
                has_engaged_confirmation=False,
            )
        )

        patterns = (
            candidates
            .values("network_hash")
            .annotate(
                hits=Count("id"),

                clients=Count(
                    "client_hash",
                    distinct=True,
                ),

                visitors=Count(
                    "visitor_hash",
                    distinct=True,
                ),

                ips=Count(
                    "ip_hash",
                    distinct=True,
                ),

                paths=Count(
                    "path",
                    distinct=True,
                ),

                uas=Count(
                    "user_agent_hash",
                    distinct=True,
                ),

                first_seen=Min("created_at"),
                last_seen=Max("created_at"),
            )
            .filter(
                clients__gte=(
                    NETWORK_DIAGNOSTIC_MIN_CLIENTS
                ),
                visitors__gte=(
                    NETWORK_DIAGNOSTIC_MIN_VISITORS
                ),
                ips__gte=(
                    NETWORK_DIAGNOSTIC_MIN_IPS
                ),
                paths__gte=(
                    NETWORK_DIAGNOSTIC_MIN_PATHS
                ),
                uas__gte=(
                    NETWORK_DIAGNOSTIC_MIN_UAS
                ),

                # Pattern logujeme jen pokud v něm
                # nedávno přibyl nový request.
                last_seen__gte=recent_start,
            )
            .order_by(
                "-clients",
                "-hits",
            )
        )

        pattern_count = 0

        for pattern in patterns:
            network_hash = pattern["network_hash"]

            sample_paths = list(
                candidates
                .filter(
                    network_hash=network_hash,
                )
                .values_list(
                    "path",
                    flat=True,
                )
                .distinct()[:6]
            )

            span_seconds = int(
                (
                    pattern["last_seen"]
                    - pattern["first_seen"]
                ).total_seconds()
            )

            logger.info(
                "NETWORK_PATTERN_CANDIDATE "
                "reason=network_multi_ua_no_engagement "
                "network=%s "
                "hits=%s "
                "clients=%s "
                "visitors=%s "
                "ips=%s "
                "paths=%s "
                "uas=%s "
                "span_seconds=%s "
                "sample_paths=%s",
                network_hash[:12],
                pattern["hits"],
                pattern["clients"],
                pattern["visitors"],
                pattern["ips"],
                pattern["paths"],
                pattern["uas"],
                span_seconds,
                "|".join(sample_paths),
            )

            pattern_count += 1

        return pattern_count    

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

        days = {
            candidate.day
            for candidate in candidates
        }

        # I když zrovna není žádný nový PENDING candidate,
        # chceme umět znovu vyhodnotit dnešní dříve KEPT
        # no_posthoc_rule_matched kandidáty.
        days.add(timezone.localdate())

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


        # -------------------------------------------------
        # RULE 5:
        # krátký distribuovaný no-JS burst:
        #
        # - EMPTY referer
        # - desktop Chrome
        # - rotující Chrome major verze
        # - mnoho různých clientů/IP
        # - mnoho různých paths
        # - každý visitor i client má jen jeden candidate
        #
        # Jednotlivý request vypadá normálně.
        # Podezřelý je až celý cluster.
        # -------------------------------------------------

        visitor_candidate_counts = defaultdict(int)
        client_candidate_counts = defaultdict(int)

        for candidate in context_working:
            visitor_candidate_counts[
                (
                    candidate.day,
                    candidate.visitor_hash,
                )
            ] += 1

            client_candidate_counts[
                (
                    candidate.day,
                    candidate.client_hash,
                )
            ] += 1

        distributed_burst_groups = defaultdict(list)

        for candidate in context_working:
            if candidate.is_social_iab:
                continue

            if (
                candidate.referer_kind
                != TrafficVisitCandidate.RefererKind.EMPTY
            ):
                continue

            if not candidate.ip_hash:
                continue

            # Každý visitor musí být čistý singleton.
            if (
                visitor_candidate_counts[
                    (
                        candidate.day,
                        candidate.visitor_hash,
                    )
                ]
                != 1
            ):
                continue

            # Totéž pro client.
            if (
                client_candidate_counts[
                    (
                        candidate.day,
                        candidate.client_hash,
                    )
                ]
                != 1
            ):
                continue

            # První verzi pravidla záměrně omezujeme
            # na observed desktop-Chrome pattern.
            if (
                get_desktop_chrome_major(
                    candidate.user_agent
                )
                is None
            ):
                continue

            distributed_burst_groups[
                candidate.day
            ].append(candidate)

        for rows in distributed_burst_groups.values():
            ids = find_distributed_no_js_chrome_bursts(
                rows,
                seconds=DISTRIBUTED_NO_JS_BURST_SECONDS,
                min_clients=(
                    DISTRIBUTED_NO_JS_BURST_MIN_CLIENTS
                ),
                min_visitors=(
                    DISTRIBUTED_NO_JS_BURST_MIN_VISITORS
                ),
                min_ips=(
                    DISTRIBUTED_NO_JS_BURST_MIN_IPS
                ),
                min_paths=(
                    DISTRIBUTED_NO_JS_BURST_MIN_PATHS
                ),
                min_chrome_majors=(
                    DISTRIBUTED_NO_JS_BURST_MIN_CHROME_MAJORS
                ),
            )

            for candidate_id in ids:
                reasons_by_candidate.setdefault(
                    candidate_id,
                    (
                        "distributed_rotating_chrome_"
                        "burst_no_engagement"
                    ),
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
                or
                DailyEngagedPageVisitor.objects.filter(
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

        # -------------------------------------------------
        # Diagnostika distribuovaných network patternů.
        #
        # Nic nemaže. Jen případný pattern zapíše
        # jako NETWORK_PATTERN_CANDIDATE do traffic.log.
        # -------------------------------------------------

        network_patterns = self.log_network_pattern_candidates(now)

        self.cleanup_old_candidates(now)

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed={len(candidates)}, "
                f"cleaned_visitors={cleaned_visitors}, "
                f"cleaned_pageviews={cleaned_pageviews}, "
                f"network_patterns={network_patterns}"
            )
        )

    def cleanup_old_candidates(self, now):
        TrafficVisitCandidate.objects.filter(
            created_at__lt=now - timedelta(days=14)
        ).delete()