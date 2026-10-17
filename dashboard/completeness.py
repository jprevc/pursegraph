"""PROTOTYPE (#75 Period completeness), throwaway: lives only on prototype/75-completeness.

How complete a Period's numbers are, from Coverage: each month is Complete, Partial (a Gap in it), In progress
(the running month, no Gap) or Not tracked (before every included Account's first Coverage day). Only the
Accounts the filters include count, and Accounts that receive no Statements never do."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import formats

from ledger.coverage import ONE_DAY, DateRange
from ledger.models import Account

from . import periods, queries
from .periods import Period

COMPLETE, PARTIAL, IN_PROGRESS, NOT_TRACKED = "complete", "partial", "in_progress", "not_tracked"
# A longer Period takes the first of these that any of its months is.
PRECEDENCE = [PARTIAL, IN_PROGRESS, NOT_TRACKED, COMPLETE]


@dataclass(frozen=True)
class AccountGap:
    account: Account
    days: DateRange

    @property
    def label(self) -> str:
        start, end = self.days.start, self.days.end
        if start.year == end.year and start.month == end.month:
            return f"{start.day}–{formats.date_format(end, 'j M')}" if start != end else formats.date_format(end, "j M")
        return f"{formats.date_format(start, 'j M')} – {formats.date_format(end, 'j M')}"


def _accounts(filters: queries.Filters) -> list[tuple[Account, list[DateRange]]]:
    accounts = Account.objects.exclude(bank="other").prefetch_related("statements")
    if filters.member:
        accounts = accounts.filter(pk__in=queries._bucket(filters.member))
    if filters.accounts:
        accounts = accounts.filter(pk__in=filters.accounts)
    return [(a, a.coverage()) for a in accounts]


def _gaps(coverage: list[DateRange], within: DateRange) -> list[DateRange]:
    """The Gap days of one Account inside `within`: from its first Coverage day up to today, not covered."""
    if not coverage:
        return []
    start, end = max(within.start, coverage[0].start), min(within.end, periods.today())
    gaps, day = [], start
    for covered in coverage:
        if covered.end < day:
            continue
        if covered.start > end:
            break
        if covered.start > day:
            gaps.append(DateRange(day, covered.start - ONE_DAY))
        day = covered.end + ONE_DAY
    if day <= end:
        gaps.append(DateRange(day, end))
    return gaps


def _state(month: Period, accounts) -> str:
    within = DateRange(month.start, month.end)
    if any(_gaps(coverage, within) for _a, coverage in accounts):
        return PARTIAL
    if not any(coverage and coverage[0].start <= month.end for _a, coverage in accounts):
        return NOT_TRACKED
    return IN_PROGRESS if month.so_far else COMPLETE


@dataclass(frozen=True)
class Completeness:
    state: str
    gaps: list[AccountGap]
    months: dict[str, str]  # month key → state
    awaiting: Decimal
    spent: Decimal

    @property
    def awaiting_share(self) -> int:
        return round(self.awaiting / self.spent * 100) if self.spent else 0

    @property
    def by_account(self) -> list[tuple[Account, str]]:
        """Each Account with a Gap, and its Gaps' days ("1–31 Jul, 16 Sep – 17 Oct")."""
        grouped: dict[Account, list[str]] = {}
        for gap in self.gaps:
            grouped.setdefault(gap.account, []).append(gap.label)
        return [(a, ", ".join(labels)) for a, labels in grouped.items()]

    def month(self, key: str) -> str:
        return self.months.get(key, COMPLETE)


def of(period: Period, filters: queries.Filters) -> Completeness:
    accounts = _accounts(filters)
    months = {queries._month_key(m): _state(m, accounts) for m in queries._months(period)}
    state = next((s for s in PRECEDENCE if s in months.values()), COMPLETE)
    within = DateRange(period.start, period.end)
    gaps = [AccountGap(a, g) for a, coverage in accounts for g in _gaps(coverage, within)]
    spending = queries._spending(period, filters)
    spent = -(spending.aggregate(t=Sum("amount"))["t"] or Decimal(0))
    awaiting = -(spending.filter(subcategory__isnull=True).aggregate(t=Sum("amount"))["t"] or Decimal(0))
    return Completeness(state, gaps, months, awaiting, spent)


def household_start() -> date | None:
    """The Household's first Coverage day, whatever the filters: where the stepper's ‹ stops."""
    starts = [c[0].start for _a, c in _accounts(queries.Filters()) if c]
    return min(starts) if starts else None


def reason(gaps: list[AccountGap], month: Period) -> str:
    """The tooltip's first line for a Partial month."""
    inside = [g for g in gaps if g.days.start <= month.end and g.days.end >= month.start]
    clipped = [AccountGap(g.account, DateRange(max(g.days.start, month.start), min(g.days.end, month.end))) for g in inside]
    return "; ".join(f"No Statements from {g.account} for {g.label}" for g in clipped)
