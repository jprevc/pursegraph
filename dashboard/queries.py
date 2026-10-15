"""The dashboard query module: given a view, a Period and filters, it returns the chart series and table rows.
The views only render what it returns.

Everywhere: Transfers are left out, Refunds net against spending in their Subcategory, and unresolved
Transactions form an "Awaiting review" bucket: on the spending side, the unresolved money out."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q, QuerySet, Sum
from django.utils.translation import gettext as _

from ledger.models import Category, Transaction

from .periods import Period

# The drill-down key of the Awaiting review bucket; Categories use their id.
AWAITING_REVIEW = "awaiting"


@dataclass(frozen=True)
class Filters:
    """Narrows every view. Empty for now: the Member and Account filters come with #32."""


@dataclass(frozen=True)
class Row:
    """One line of a view's table. A top-level row is also a chart mark, and its `key` names the Transactions
    behind it for the drill-down."""

    label: str
    amount: Decimal
    key: str | None
    children: list["Row"] = field(default_factory=list)


@dataclass(frozen=True)
class ViewData:
    rows: list[Row]
    total: Decimal

    @property
    def series(self) -> list[dict]:
        """The chart's marks, one per row."""
        return [{"name": r.label, "value": float(r.amount), "key": r.key} for r in self.rows]


def _transactions(period: Period, filters: Filters) -> QuerySet[Transaction]:
    return Transaction.objects.filter(
        date__gte=period.start, date__lte=period.end, is_transfer=False
    )


def _spending(period: Period, filters: Filters) -> QuerySet[Transaction]:
    """What Spending by Category counts: spending Subcategories, Refunds included, and unresolved money out."""
    return _transactions(period, filters).filter(
        Q(subcategory__category__kind=Category.Kind.SPENDING)
        | Q(subcategory__isnull=True, amount__lt=0)
    )


def spending_by_category(period: Period, filters: Filters) -> ViewData:
    """Spending per Category, biggest first, each with its Subcategories, then the Awaiting review bucket."""
    spent = _spending(period, filters).values("subcategory").annotate(total=-Sum("amount"))
    # None is the unresolved money out.
    by_subcategory: dict[int | None, Decimal] = {s["subcategory"]: s["total"] for s in spent}
    rows = []
    for category in Category.objects.filter(kind=Category.Kind.SPENDING).prefetch_related(
        "subcategories"
    ):
        children = [
            Row(s.name, by_subcategory[s.pk], None)
            for s in category.subcategories.all()
            if s.pk in by_subcategory
        ]
        if children:
            rows.append(
                Row(
                    category.name,
                    sum((c.amount for c in children), Decimal(0)),
                    str(category.pk),
                    children,
                )
            )
    rows.sort(key=lambda r: r.amount, reverse=True)
    if None in by_subcategory:
        rows.append(Row(_("Awaiting review"), by_subcategory[None], AWAITING_REVIEW))
    return ViewData(rows, sum((r.amount for r in rows), Decimal(0)))


def spending_transactions(period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    """The Transactions behind one Spending by Category mark, as the drill-down lists them."""
    spending = _spending(period, filters)
    if key == AWAITING_REVIEW:
        return spending & Transaction.objects.unresolved()
    if key.isdigit():
        return spending.filter(subcategory__category=int(key))
    return spending.none()


VIEWS = {"spending": spending_by_category}
DRILL_DOWNS = {"spending": spending_transactions}


def view_data(view: str, period: Period, filters: Filters) -> ViewData:
    return VIEWS[view](period, filters)


def drill_down(view: str, period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    return DRILL_DOWNS[view](period, filters, key)
