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


def gaps(ranges: list[DateRange]) -> list[DateRange]:
    """The missing days between the date ranges of a Coverage."""
    return [
        DateRange(before.end + ONE_DAY, after.start - ONE_DAY) for before, after in pairwise(ranges)
    ]


@dataclass(frozen=True)
class Segment:
    """One stretch of a Coverage timeline: covered days, or a gap between them."""

    range: DateRange
    is_gap: bool


def timeline(ranges: list[DateRange]) -> list[Segment]:
    """The Coverage from its first to its last day, as covered stretches with the gaps between them."""
    if not ranges:
        return []
    segments = [Segment(ranges[0], is_gap=False)]
    # Each gap is followed by the range after it.
    for gap, covered in zip(gaps(ranges), ranges[1:], strict=True):
        segments += [Segment(gap, is_gap=True), Segment(covered, is_gap=False)]
    return segments
