"""Coverage: the dates of an Account for which Statements have been imported, derived from its Statements."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise

ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class DateRange:
    """The days from `start` to `end`, both included."""

    start: date
    end: date

    def __contains__(self, day: date) -> bool:
        return self.start <= day <= self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def coverage(statements: Iterable) -> list[DateRange]:
    """The Statements' periods merged into separate date ranges, in date order. Adjacent periods merge."""
    ranges: list[DateRange] = []
    for start, end in sorted((s.period_start, s.period_end) for s in statements):
        if ranges and start <= ranges[-1].end + ONE_DAY:
            if end > ranges[-1].end:
                ranges[-1] = DateRange(ranges[-1].start, end)
        else:
            ranges.append(DateRange(start, end))
    return ranges


def gaps(ranges: list[DateRange], until: date | None = None) -> list[DateRange]:
    """The missing days between the date ranges of a Coverage and, `until` a day (today, for a Gap), those since
    its last one."""
    missing = [
        DateRange(before.end + ONE_DAY, after.start - ONE_DAY) for before, after in pairwise(ranges)
    ]
    if ranges and until and ranges[-1].end < until:
        missing.append(DateRange(ranges[-1].end + ONE_DAY, until))
    return missing


@dataclass(frozen=True)
class Shrink:
    """What a Statement's days become once it is deleted: Gaps, or untracked, before the Account's first Coverage
    day. Days other Statements still cover, and days after today, are neither."""

    gaps: list[DateRange]
    untracked: list[DateRange]


def removing(period: DateRange, others: list[DateRange], until: date) -> Shrink:
    """What deleting the Statement over `period` leaves, when the Account's other Statements cover `others`."""
    first = others[0].start if others else None
    shrink = Shrink([], [])
    day = period.start
    while day <= min(period.end, until):
        if not any(day in r for r in others):
            runs = shrink.gaps if first and day > first else shrink.untracked
            if runs and runs[-1].end + ONE_DAY == day:
                runs[-1] = DateRange(runs[-1].start, day)
            else:
                runs.append(DateRange(day, day))
        day += ONE_DAY
    return shrink
