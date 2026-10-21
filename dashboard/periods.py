"""The dashboard's period: a Month, Quarter, Year, Last 12 months or Custom range, written in the URL as one
`period` token, such as "2026-09", "2026-Q3", "2026", "last12-2026-09" or "2026-09-10..2026-09-19"."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from pursegraph import figures

UNITS = [
    ("month", gettext_lazy("Month")),
    ("quarter", gettext_lazy("Quarter")),
    ("year", gettext_lazy("Year")),
    ("last12", gettext_lazy("Last 12 months")),
    ("custom", gettext_lazy("Custom range")),
]


# The years a Period may cover: far enough from the calendar's ends for every Period it links to.
YEARS = range(1900, 3000)


def today() -> date:
    return timezone.localdate()


def _month_start(year: int, month: int) -> date:
    """The first day of a month, with `month` allowed outside 1–12 to step across years."""
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return date(year, month, 1)


def _quarter_of(day: date) -> int:
    return (day.month + 2) // 3


def _month_end(year: int, month: int) -> date:
    return _month_start(year, month + 1) - timedelta(days=1)


@dataclass(frozen=True)
class Period:
    unit: str
    start: date
    end: date

    @classmethod
    def month(cls, year: int, month: int) -> "Period":
        return cls("month", _month_start(year, month), _month_end(year, month))

    @classmethod
    def quarter(cls, year: int, quarter: int) -> "Period":
        first = _month_start(year, 3 * quarter - 2)
        return cls("quarter", first, _month_end(first.year, first.month + 2))

    @classmethod
    def year(cls, year: int) -> "Period":
        return cls("year", date(year, 1, 1), date(year, 12, 31))

    @classmethod
    def last12(cls, year: int, month: int) -> "Period":
        """The 12 months ending with `month`."""
        first = _month_start(year, month - 11)
        return cls("last12", first, _month_end(year, month))

    @classmethod
    def default(cls) -> "Period":
        """The last complete month."""
        now = today()
        return cls.month(now.year, now.month - 1)

    @classmethod
    def last_12_months(cls) -> "Period":
        """The Category trends' default: the 12 months up to the current one."""
        now = today()
        return cls.last12(now.year, now.month)

    @classmethod
    def parse(cls, token: str, default: "Callable[[], Period] | None" = None) -> "Period":
        """The Period a `period` token names; the default (the last complete month, unless given) for anything
        else."""
        try:
            period = cls._read(token)
        except ValueError:
            period = None
        return period if period and period.in_bounds else (default or cls.default)()

    @classmethod
    def _read(cls, token: str) -> "Period | None":
        if m := re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", token):
            return cls.month(int(m[1]), int(m[2]))
        if m := re.fullmatch(r"(\d{4})-Q([1-4])", token):
            return cls.quarter(int(m[1]), int(m[2]))
        if m := re.fullmatch(r"(\d{4})", token):
            return cls.year(int(m[1]))
        if m := re.fullmatch(r"last12-(\d{4})-(0[1-9]|1[0-2])", token):
            return cls.last12(int(m[1]), int(m[2]))
        if m := re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", token):
            first, last = sorted([date.fromisoformat(m[1]), date.fromisoformat(m[2])])
            return cls("custom", first, last)
        return None

    @classmethod
    def custom(
        cls, start: str, end: str, default: "Callable[[], Period] | None" = None
    ) -> "Period":
        """A Custom range from two ISO dates, in either order; the default if either can't be read."""
        return cls.parse(f"{start}..{end}", default)

    @property
    def in_bounds(self) -> bool:
        """Within YEARS, so that its neighbours and its other units, which the period selector links to, exist too."""
        return self.start.year in YEARS and self.end.year in YEARS

    @classmethod
    def from_query(cls, params, default: "Callable[[], Period] | None" = None) -> "Period":
        """The Period in a request's query: `period`, or a Custom range's `from` and `to`."""
        if params.get("from") and params.get("to"):
            return cls.custom(params["from"], params["to"], default)
        return cls.parse(params.get("period", ""), default)

    @property
    def token(self) -> str:
        if self.unit == "month":
            return f"{self.start:%Y-%m}"
        if self.unit == "quarter":
            return f"{self.start.year}-Q{_quarter_of(self.start)}"
        if self.unit == "year":
            return str(self.start.year)
        if self.unit == "last12":
            return f"last12-{self.end:%Y-%m}"
        return f"{self.start.isoformat()}..{self.end.isoformat()}"

    def as_unit(self, unit: str) -> "Period":
        """The Period of `unit` holding this one's last month, so switching units stays near the same dates."""
        last = min(self.end, today())
        if unit == "month":
            return Period.month(last.year, last.month)
        if unit == "quarter":
            return Period.quarter(last.year, _quarter_of(last))
        if unit == "year":
            return Period.year(last.year)
        if unit == "last12":
            return Period.last12(last.year, last.month)
        return Period("custom", self.start, self.end)

    def units(self) -> list[tuple[str, str, bool]]:
        """The period selector's options: each unit's token, label and whether it is this Period's unit."""
        return [(self.as_unit(unit).token, str(label), unit == self.unit) for unit, label in UNITS]

    def step(self, direction: int) -> "Period":
        """The Period one unit before (-1) or after (+1) this one."""
        if self.unit == "custom":
            length = self.end - self.start + timedelta(days=1)
            return Period("custom", self.start + direction * length, self.end + direction * length)
        months = {"month": 1, "quarter": 3, "year": 12, "last12": 1}[self.unit]
        start = _month_start(self.start.year, self.start.month + direction * months)
        end = _month_end(self.end.year, self.end.month + direction * months)
        return Period(self.unit, start, end)

    @property
    def previous(self) -> "Period":
        return self.step(-1)

    @property
    def next(self) -> "Period | None":
        """The Period after this one, unless it lies wholly in the future."""
        following = self.step(1)
        return following if following.start <= today() else None

    @property
    def label(self) -> str:
        if self.unit == "month":
            return figures.month(self.start)
        if self.unit == "quarter":
            return _("Q%(quarter)s %(year)s") % {
                "quarter": _quarter_of(self.start),
                "year": self.start.year,
            }
        if self.unit == "year":
            return str(self.start.year)
        return figures.date_range(self.start, self.end)

    @property
    def so_far(self) -> date | None:
        """Today, while the Period is still running."""
        now = today()
        return now if self.start <= now <= self.end else None
