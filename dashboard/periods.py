"""The dashboard's period: a Month, Quarter, Year, Last 12 months or Custom range, written in the URL as one
`period` token, such as "2026-09", "2026-Q3", "2026", "last12-2026-09" or "2026-09-10..2026-09-19"."""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

UNITS = [
    ("month", gettext_lazy("Month")),
    ("quarter", gettext_lazy("Quarter")),
    ("year", gettext_lazy("Year")),
    ("last12", gettext_lazy("Last 12 months")),
    ("custom", gettext_lazy("Custom range")),
]


def today() -> date:
    return timezone.localdate()


def _month_start(year: int, month: int) -> date:
    """The first day of a month, with `month` allowed outside 1–12 to step across years."""
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return date(year, month, 1)


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
    def parse(cls, token: str) -> "Period":
        """The Period a `period` token names; the default for anything else."""
        try:
            if m := re.fullmatch(r"(\d{4})-(\d{2})", token):
                if 1 <= int(m[2]) <= 12:
                    return cls.month(int(m[1]), int(m[2]))
            elif m := re.fullmatch(r"(\d{4})-Q([1-4])", token):
                return cls.quarter(int(m[1]), int(m[2]))
            elif m := re.fullmatch(r"(\d{4})", token):
                return cls.year(int(m[1]))
            elif m := re.fullmatch(r"last12-(\d{4})-(\d{2})", token):
                if 1 <= int(m[2]) <= 12:
                    return cls.last12(int(m[1]), int(m[2]))
            elif m := re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", token):
                return cls.custom(m[1], m[2])
        except ValueError:
            pass
        return cls.default()

    @classmethod
    def custom(cls, start: str, end: str) -> "Period":
        """A Custom range from two ISO dates, in either order; the default if either can't be read."""
        try:
            first, last = sorted([date.fromisoformat(start), date.fromisoformat(end)])
        except ValueError:
            return cls.default()
        return cls("custom", first, last)

    @classmethod
    def from_query(cls, params) -> "Period":
        """The Period in a request's query: `period`, or a Custom range's `from` and `to`."""
        if params.get("from") and params.get("to"):
            return cls.custom(params["from"], params["to"])
        return cls.parse(params.get("period", ""))

    @property
    def token(self) -> str:
        if self.unit == "month":
            return f"{self.start:%Y-%m}"
        if self.unit == "quarter":
            return f"{self.start.year}-Q{(self.start.month + 2) // 3}"
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
            return Period.quarter(last.year, (last.month + 2) // 3)
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
            return formats.date_format(self.start, "F Y")
        if self.unit == "quarter":
            return _("Q%(quarter)s %(year)s") % {
                "quarter": (self.start.month + 2) // 3,
                "year": self.start.year,
            }
        if self.unit == "year":
            return str(self.start.year)
        pattern = "M Y" if self.unit == "last12" else "j M Y"
        return (
            f"{formats.date_format(self.start, pattern)} – {formats.date_format(self.end, pattern)}"
        )

    @property
    def so_far(self) -> date | None:
        """Today, while the Period is still running."""
        now = today()
        return now if self.start <= now < self.end else None
