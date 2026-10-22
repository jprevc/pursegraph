"""Period completeness (docs/design/period-completeness.md): how complete a Period's numbers are, read from the
Coverage of the Accounts the filters include. Derived and read-only, like Coverage itself.

Accounts that receive no Statements are never considered, and neither are those with no Statement yet: nothing is
known about them."""

from dataclasses import dataclass
from datetime import date

from django.utils import formats
from django.utils.translation import gettext as _

from ledger.coverage import DateRange, gaps
from ledger.models import Account
from pursegraph import figures

from . import periods
from .periods import Period

COMPLETE = "complete"
PARTIAL = "partial"
PARTLY_TRACKED = "partly_tracked"
IN_PROGRESS = "in_progress"
NOT_TRACKED = "not_tracked"
# A longer Period takes the first of these that any of its months is.
PRECEDENCE = [PARTIAL, PARTLY_TRACKED, IN_PROGRESS, NOT_TRACKED, COMPLETE]


@dataclass(frozen=True)
class Covered:
    """An Account that has Coverage, and its Coverage."""

    account: Account
    ranges: list[DateRange]

    @property
    def first_day(self) -> date:
        """Its first Coverage day: before it, the Account isn't tracked yet."""
        return self.ranges[0].start


def _covered(accounts) -> list[Covered]:
    """Each of `accounts` that receives Statements and has Coverage."""
    covered = []
    for account in accounts.prefetch_related("statements"):
        if account.receives_statements and (ranges := account.coverage()):
            covered.append(Covered(account, ranges))
    return covered


def _overlaps(a: DateRange | Period, b: DateRange | Period) -> bool:
    """Whether two stretches of days share one."""
    return a.start <= b.end and a.end >= b.start


def household_start() -> date | None:
    """The Household's first Coverage day, whatever the filters: where the period stepper stops."""
    return min((c.first_day for c in _covered(Account.objects.all())), default=None)


def qualifier(state: str) -> str:
    """What a table's month or a title adds for a state: "(partial)"; empty for Complete and Not tracked."""
    return {
        PARTIAL: _("(partial)"),
        PARTLY_TRACKED: _("(partly tracked)"),
        IN_PROGRESS: _("(so far)"),
    }.get(state, "")


@dataclass(frozen=True)
class AccountGap:
    """The days of a Gap of `account` within some Period."""

    account: Account
    days: DateRange

    @property
    def label(self) -> str:
        """Its days, the year left to the period around it: "1–31 Jul"."""
        return figures.date_range(self.days.start, self.days.end, year=False)


def _tracked_from(account: Account, start: date) -> str:
    """ "Joint Revolut is tracked from 1 Feb 2026"."""
    return _("%(account)s is tracked from %(date)s") % {
        "account": account.name,
        "date": figures.day(start),
    }


@dataclass(frozen=True)
class Month:
    """One month of a Period, in one of the month states, and why it is in it (empty for Complete)."""

    period: Period
    state: str
    reason: str

    @property
    def key(self) -> str:
        """The month's key in a view's chart and drill-downs: "2026-07"."""
        return f"{self.period.start:%Y-%m}"

    @property
    def not_tracked(self) -> bool:
        return self.state == NOT_TRACKED

    @property
    def qualifier(self) -> str:
        return qualifier(self.state)


@dataclass(frozen=True)
class Completeness:
    """How complete a Period is: its state, its months', the Gaps within it and the Accounts tracked only from some
    day within it."""

    state: str
    months: list[Month]
    gaps: list[AccountGap]
    tracked_from: list[tuple[Account, date]]

    def month(self, key: str) -> Month | None:
        """The month of the Period that `key` names, if any."""
        return next((m for m in self.months if m.key == key), None)

    def months_of(self, keys: list[str]) -> list[Month | None]:
        """The months the `keys` of a chart over months name, in their order."""
        return [self.month(key) for key in keys]

    @property
    def gaps_by_account(self) -> list[tuple[Account, str]]:
        """Each Account with a Gap, and its Gaps' days: "1–31 Jul, 1–17 Oct"."""
        days: dict[Account, list[str]] = {}
        for gap in self.gaps:
            days.setdefault(gap.account, []).append(gap.label)
        return [(account, ", ".join(labels)) for account, labels in days.items()]

    @property
    def tracked_from_labels(self) -> list[str]:
        """What the header line says of each Account tracked only from some day within the Period."""
        return [_tracked_from(account, start) for account, start in self.tracked_from]


class Tracking:
    """The Coverage of the Accounts some filters include, read once to judge any number of Periods."""

    def __init__(self, included):
        self.accounts = _covered(included)
        self.today = periods.today()
        self._gaps = [
            (c.account, g) for c in self.accounts for g in gaps(c.ranges, until=self.today)
        ]

    def _gaps_within(self, period: Period) -> list[AccountGap]:
        """The Gaps of the Accounts within `period`, cut to it."""
        return [
            AccountGap(a, DateRange(max(g.start, period.start), min(g.end, period.end)))
            for a, g in self._gaps
            if _overlaps(g, period)
        ]

    def _tracked_later(self, month: Period) -> list[tuple[Account, date]]:
        """The Accounts first tracked after the start of `month`, earliest first."""
        later = [(c.account, c.first_day) for c in self.accounts if c.first_day > month.start]
        return sorted(later, key=lambda pair: pair[1])

    def month(self, month: Period) -> Month:
        """The state of `month`, the first of Partial, Not tracked, Partly tracked and In progress that it is, or
        else Complete; a month after today is never judged."""
        today = self.today
        if month.start > today:
            return Month(month, COMPLETE, "")
        if gaps_in := self._gaps_within(month):
            return Month(
                month,
                PARTIAL,
                "; ".join(
                    _("No Statements from %(account)s for %(days)s")
                    % {"account": g.account.name, "days": g.label}
                    for g in gaps_in
                ),
            )
        if self.accounts and all(c.first_day > month.end for c in self.accounts):
            return Month(month, NOT_TRACKED, _("No Statements yet"))
        if later := self._tracked_later(month):
            return Month(month, PARTLY_TRACKED, "; ".join(_tracked_from(a, d) for a, d in later))
        if month.start <= today <= month.end:
            so_far = formats.date_format(today, "MONTH_DAY_FORMAT")
            return Month(month, IN_PROGRESS, _("So far, to %(date)s") % {"date": so_far})
        return Month(month, COMPLETE, "")

    def completeness(self, period: Period) -> Completeness:
        """How complete `period` is: the first state any of its months is, in PRECEDENCE."""
        months = [self.month(m) for m in period.months]
        states = {m.state for m in months}
        # Not tracked yet during a part of the Period in which another Account is, whatever state that part is in.
        tracked_from: dict[Account, date] = {}
        for m in months:
            if m.state != NOT_TRACKED and m.period.start <= self.today:
                tracked_from.update(self._tracked_later(m.period))
        return Completeness(
            next(s for s in PRECEDENCE if s in states or s == COMPLETE),
            months,
            self._gaps_within(period),
            sorted(tracked_from.items(), key=lambda pair: pair[1]),
        )


def not_comparable(period: Period, tracking: Tracking) -> str | None:
    """Why the stat tiles can't compare `period` with the one before, if either isn't Complete: naming the
    incomplete month, the period's own if both are ("Not comparable: July is incomplete")."""
    for judged in map(tracking.completeness, (period, period.previous)):
        # The month that makes the period incomplete: the first in its state.
        if month := next((m for m in judged.months if m.state == judged.state != COMPLETE), None):
            same_year = month.period.start.year == period.end.year
            name = (
                formats.date_format(month.period.start, "F")
                if same_year
                else figures.month(month.period.start)
            )
            return _("Not comparable: %(month)s is incomplete") % {"month": name}
    return None


def _months(start: date, end: date) -> str:
    """A stretch of months: "Jul 2026", "Jan – Oct 2026", "Dec 2025 – Feb 2026"."""
    if (start.year, start.month) == (end.year, end.month):
        return figures.month_short(start)
    first = figures.month_short(start, year=start.year != end.year)
    return f"{first} – {figures.month_short(end)}"


@dataclass(frozen=True)
class Stretch:
    """On the Not tracked card's timeline, the months with Statements in a row, or one month without: from month
    column `column` (counting from 1), `span` months long."""

    column: int
    span: int
    tracked: bool


@dataclass(frozen=True)
class Columns:
    """Month columns on the Not tracked card's timeline: from `column` (counting from 1), `span` months long."""

    column: int
    span: int


@dataclass(frozen=True)
class TimelineRow:
    """One Account's row on the Not tracked card's timeline."""

    account: Account
    stretches: list[Stretch]
    months: list[Period]

    @property
    def description(self) -> str:
        """The stretches with Statements, in words: "Jan – Jun 2026, Aug – Sep 2026"."""
        return ", ".join(
            _months(self.months[s.column - 1].start, self.months[s.column + s.span - 2].start)
            for s in self.stretches
            if s.tracked
        )


@dataclass(frozen=True)
class NotTracked:
    """What the Not tracked card shows for a Period wholly before every included Account's first Coverage day:
    from when they are tracked, the first Period of its unit that is, and their Coverage month by month, from the
    Household's first Coverage month to the running month, with the shown Period's months picked out."""

    accounts: list[Account]
    tracked_from: date
    first_period: Period
    months: list[Period]
    rows: list[TimelineRow]
    shown: Columns | None

    @property
    def columns(self) -> list[tuple[Period, bool]]:
        """Each month column, and whether the shown Period holds it."""
        first, span = (self.shown.column, self.shown.span) if self.shown else (0, 0)
        return [(m, first <= i < first + span) for i, m in enumerate(self.months, start=1)]


def not_tracked(period: Period, tracking: Tracking, household_start: date) -> NotTracked:
    """The Not tracked card for `period`, which the included Accounts' Coverage starts after."""
    tracked_from = min(c.first_day for c in tracking.accounts)
    months = Period("custom", household_start.replace(day=1), tracking.today).months
    rows = []
    for covered in tracking.accounts:
        stretches: list[Stretch] = []
        for column, month in enumerate(months, start=1):
            tracked = any(_overlaps(r, month) for r in covered.ranges)
            if tracked and stretches and stretches[-1].tracked:
                stretches[-1] = Stretch(stretches[-1].column, stretches[-1].span + 1, True)
            else:
                stretches.append(Stretch(column, 1, tracked))
        rows.append(TimelineRow(covered.account, stretches, months))
    shown = [i for i, m in enumerate(months, start=1) if _overlaps(m, period)]
    return NotTracked(
        [c.account for c in tracking.accounts],
        tracked_from,
        Period.containing(period.unit, tracked_from),
        months,
        rows,
        Columns(shown[0], len(shown)) if shown else None,
    )


def mark_months(chart: dict, completeness: Completeness) -> None:
    """Gives a chart over months (its `keys`) each month's state and reason, the running month's key, whatever
    its state, and a Not tracked month no figures rather than zeros, so that bars are missing and lines break."""
    months = completeness.months_of(chart["keys"])
    chart["running"] = f"{periods.today():%Y-%m}"
    chart["states"] = [m.state if m else COMPLETE for m in months]
    chart["reasons"] = [m.reason if m else "" for m in months]
    tracked = [state != NOT_TRACKED for state in chart["states"]]

    def blank(values: list) -> list:
        return [v if t else None for v, t in zip(values, tracked, strict=True)]

    for name in ("in", "out", "net", "others"):
        if name in chart:
            chart[name] = blank(chart[name])
    for line in chart.get("lines", []):
        line["data"] = blank(line["data"])
