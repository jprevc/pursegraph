"""The Accounts board (docs/design/import.md): every Account's Coverage on one shared time axis, from the Household's
first covered day to today, with the stretch an import just added and the Gaps up to today."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from django.utils.translation import gettext as _

from pursegraph import figures

from .coverage import ONE_DAY, DateRange, gaps

# A Gap's label shows only where its slot is wider than this share of the axis.
LABEL_FITS = 2.2


@dataclass(frozen=True)
class Tick:
    """A quarter on the axis: its month, or at January its year."""

    day: date
    label: str
    is_year: bool
    left: float


@dataclass(frozen=True)
class Axis:
    """From `start` to the end of `today`, placed as percentages of its width."""

    start: date
    today: date

    def at(self, day: date) -> float:
        span = (self.today + ONE_DAY - self.start).days
        return (day - self.start).days / span * 100

    def ticks(self) -> list[Tick]:
        ticks = []
        year, month = self.start.year, self.start.month
        while (day := date(year, month, 1)) <= self.today:
            if day > self.start and month % 3 == 1:
                is_year = month == 1
                label = str(year) if is_year else figures.month_short(day, year=False)
                ticks.append(Tick(day, label, is_year, self.at(day)))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return ticks


Kind = Literal["covered", "new", "gap"]


@dataclass(frozen=True)
class Stretch:
    """One stretch of an Account's track: covered days, the days this import added, or a Gap."""

    range: DateRange
    kind: Kind
    left: float
    width: float
    since_last_statement: bool = False

    @property
    def is_gap(self) -> bool:
        return self.kind == "gap"

    @property
    def label(self) -> str:
        """A Gap's months, when it is whole months ("Jul", "Jul–Aug"), else its length in days ("49 d")."""
        start, end = self.range.start, self.range.end
        whole_months = start.day == 1 and (end + ONE_DAY).day == 1
        if self.since_last_statement or not whole_months:
            return _("%(days)s d") % {"days": self.range.days}
        first = figures.month_short(start, year=False)
        if (start.year, start.month) == (end.year, end.month):
            return first
        return f"{first}–{figures.month_short(end, year=False)}"

    @property
    def label_fits(self) -> bool:
        return self.width > LABEL_FITS


def track(axis: Axis, ranges: list[DateRange], *, before: list[DateRange]) -> list[Stretch]:
    """An Account's Coverage `ranges` from their first day to today: what was covered `before` this import, what it
    added, and the Gaps, the last of them since the last Statement."""
    covered = [
        (DateRange(start, end), kind) for r in ranges for start, end, kind in _split(r, before)
    ]
    missing = gaps(ranges, until=axis.today)
    stretches = [
        _place(axis, r, kind)
        for r, kind in sorted([*covered, *((g, "gap") for g in missing)], key=lambda s: s[0].start)
    ]
    if stretches and stretches[-1].is_gap and stretches[-1].range.end == axis.today:
        last = stretches[-1]
        stretches[-1] = Stretch(last.range, "gap", last.left, last.width, since_last_statement=True)
    return stretches


def _split(covered: DateRange, before: list[DateRange]) -> list[tuple[date, date, Kind]]:
    """`covered` as runs of days covered `before` and days new since."""
    runs: list[tuple[date, date, Kind]] = []
    day = covered.start
    while day <= covered.end:
        kind: Kind = "covered" if any(day in r for r in before) else "new"
        if runs and runs[-1][2] == kind:
            runs[-1] = (runs[-1][0], day, kind)
        else:
            runs.append((day, day, kind))
        day += timedelta(days=1)
    return runs


def _place(axis: Axis, r: DateRange, kind: Kind) -> Stretch:
    left = axis.at(r.start)
    return Stretch(r, kind, left, axis.at(r.end + ONE_DAY) - left)
