"""The dashboard query module: given a view, a Period and filters, it returns the chart series and table rows.
The views only render what it returns.

Everywhere: Transfers are left out, Refunds net against spending in their Subcategory, and unresolved
Transactions form an "Awaiting review" bucket: on the spending side, the unresolved money out."""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import IntegerField, OuterRef, Q, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import formats
from django.utils.translation import gettext as _

from ledger.models import Account, AccountIBAN, Category, Subcategory, Transaction

from . import periods
from .periods import Period

# The drill-down key of the Awaiting review bucket; Categories use their id.
AWAITING_REVIEW = "awaiting"
# The drill-down key of the Joint bucket in Per Member; Members use their id.
JOINT = "joint"
# The drill-down key of what Transfers moved to or from other Members, under a Member filter.
OTHERS = "others"


@dataclass(frozen=True)
class Filters:
    """Narrows every view to the Accounts of one Per Member bucket, `member` (a Member's key, or the Joint one),
    and to the chosen `accounts`; nothing chosen means all of them."""

    member: str | None = None
    accounts: frozenset[int] = frozenset()

    @classmethod
    def from_query(cls, params) -> "Filters":
        """The filters in a request's query, `member` and any number of `account`; unknown ones are ignored."""
        of_account, _labels = _buckets()
        member = params.get("member")
        chosen = {int(a) for a in params.getlist("account") if a.isdigit()}
        return cls(
            member if member in of_account.values() else None,
            frozenset(chosen & of_account.keys()),
        )

    @property
    def params(self) -> list[tuple[str, str]]:
        """The query parameters that name these filters."""
        member = [("member", self.member)] if self.member else []
        return member + [("account", str(a)) for a in sorted(self.accounts)]

    def scope(self) -> Q:
        """The Transactions in the filtered Accounts."""
        q = Q()
        if self.member:
            q &= Q(account__in=_bucket(self.member))
        if self.accounts:
            q &= Q(account__in=self.accounts)
        return q


@dataclass(frozen=True)
class Row:
    """One line of a view's table. A top-level row is also a chart mark, and its `key` names the Transactions
    behind it for the drill-down."""

    label: str
    amount: Decimal
    key: str | None
    children: list["Row"] = field(default_factory=list)


@dataclass(frozen=True)
class Flow:
    """Money in against money out, for one month of Cashflow or its whole Period. Under a Member filter, `others`
    is what Transfers moved to (negative) or from other Members, so that the net is what the balance moved by."""

    label: str
    key: str | None
    money_in: Decimal
    money_out: Decimal
    others: Decimal | None = None

    @property
    def net(self) -> Decimal:
        return self.money_in - self.money_out + (self.others or Decimal(0))


@dataclass(frozen=True)
class Trend:
    """One Category's spending in each month of Category trends."""

    label: str
    key: str
    amounts: list[Decimal]

    @property
    def total(self) -> Decimal:
        return sum(self.amounts, Decimal(0))


@dataclass(frozen=True)
class ViewData:
    """What a view shows: its table's rows and total, and the data its chart is drawn from."""

    rows: list[Any]
    total: Any
    chart: dict


# Money out is spending, Refunds netted in, and unresolved money out; money in is income and unresolved money in.
MONEY_OUT = Q(subcategory__category__kind=Category.Kind.SPENDING) | Q(
    subcategory__isnull=True, amount__lt=0
)
MONEY_IN = Q(subcategory__category__kind=Category.Kind.INCOME) | Q(
    subcategory__isnull=True, amount__gt=0
)


def _transactions(period: Period, filters: Filters) -> QuerySet[Transaction]:
    return Transaction.objects.filter(
        filters.scope(), date__gte=period.start, date__lte=period.end, is_transfer=False
    )


def _to_other_members(period: Period, filters: Filters) -> QuerySet[Transaction]:
    """Under a Member filter, the Transfers between the filtered Accounts and other Members' Accounts: those whose
    other side, the paired counterpart or else the Account of the counterparty IBAN, is outside the Member's
    bucket. A Transfer whose other side isn't known is left out, as it can't be told apart from one of the
    Member's own."""
    if not filters.member:
        return Transaction.objects.none()
    other_account = Coalesce(
        "counterpart__account",
        Subquery(
            AccountIBAN.objects.filter(iban=OuterRef("counterparty_iban")).values("account")[:1]
        ),
        output_field=IntegerField(),
    )
    return (
        Transaction.objects.filter(
            filters.scope(), date__gte=period.start, date__lte=period.end, is_transfer=True
        )
        .alias(other_account=other_account)
        .filter(other_account__isnull=False)
        .exclude(other_account__in=_bucket(filters.member))
    )


def _all_money(period: Period, filters: Filters) -> QuerySet[Transaction]:
    """Money in, money out and, under a Member filter, the Transfers to or from other Members."""
    return Transaction.objects.filter(
        Q(pk__in=_transactions(period, filters).filter(MONEY_IN | MONEY_OUT).values("pk"))
        | Q(pk__in=_to_other_members(period, filters).values("pk"))
    )


def _spending(period: Period, filters: Filters) -> QuerySet[Transaction]:
    """What Spending by Category counts: spending Subcategories, Refunds included, and unresolved money out."""
    return _transactions(period, filters).filter(MONEY_OUT)


def _months(period: Period) -> list[Period]:
    """The months a Period touches, each cut to the Period."""
    months = []
    day = period.start
    while day <= period.end:
        month = Period.month(day.year, day.month)
        months.append(Period("month", max(month.start, period.start), min(month.end, period.end)))
        day = month.end + timedelta(days=1)
    return months


def _months_shown(period: Period, with_data: Iterable[str]) -> list[Period]:
    """The months of a Period a chart over time shows: those up to the current one, quiet ones too, and any later
    one holding Transactions (`with_data` are their keys)."""
    with_data = set(with_data)
    return [m for m in _months(period) if m.start <= periods.today() or _month_key(m) in with_data]


def _month_key(month: Period) -> str:
    return f"{month.start:%Y-%m}"


def _month_in(period: Period, key: str) -> Period | None:
    """The month of `period` that `key` names, if any."""
    return next((m for m in _months(period) if _month_key(m) == key), None)


def _month_label(month: Period) -> str:
    """Short, as months sit side by side on a chart's axis."""
    return formats.date_format(month.start, "M Y")


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
    bars = [{"name": r.label, "value": float(r.amount), "key": r.key} for r in rows]
    return ViewData(rows, sum((r.amount for r in rows), Decimal(0)), {"bars": bars})


def spending_transactions(period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    """The Transactions behind one Spending by Category mark, as the drill-down lists them."""
    spending = _spending(period, filters)
    if key == AWAITING_REVIEW:
        return spending & Transaction.objects.unresolved()
    if key.isdigit():
        return spending.filter(subcategory__category=int(key))
    return spending.none()


def cashflow(period: Period, filters: Filters) -> ViewData:
    """Money in against money out per month, and under a Member filter what Transfers moved to or from other
    Members. A month's key drills into all of it; with ":in", ":out" or ":others", one side."""
    by_month = {
        f"{m['month']:%Y-%m}": (m["money_in"] or Decimal(0), m["money_out"] or Decimal(0))
        for m in _transactions(period, filters)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            money_in=Sum("amount", filter=MONEY_IN), money_out=-Sum("amount", filter=MONEY_OUT)
        )
    }
    others = {
        f"{m['month']:%Y-%m}": m["total"]
        for m in _to_other_members(period, filters)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
    }
    shown = by_month.keys() | others.keys()
    nothing = (Decimal(0), Decimal(0))
    rows = [
        Flow(
            _month_label(m),
            _month_key(m),
            *by_month.get(_month_key(m), nothing),
            others.get(_month_key(m), Decimal(0)) if filters.member else None,
        )
        for m in _months_shown(period, shown)
        if shown  # none at all when the whole Period is quiet
    ]
    total = Flow(
        _("Total"),
        None,
        sum((r.money_in for r in rows), Decimal(0)),
        sum((r.money_out for r in rows), Decimal(0)),
        sum((r.others or Decimal(0) for r in rows), Decimal(0)) if filters.member else None,
    )
    labels = {"in": _("Money in"), "out": _("Money out"), "net": _("Net")}
    chart: dict[str, Any] = {
        "months": [r.label for r in rows],
        "keys": [r.key for r in rows],
        "in": [float(r.money_in) for r in rows],
        "out": [float(r.money_out) for r in rows],
        "net": [float(r.net) for r in rows],
        "labels": labels,
    }
    if filters.member:
        chart["others"] = [float(r.others or 0) for r in rows]
        labels["others"] = _("To/from other Members")
    return ViewData(rows, total, chart)


def cashflow_transactions(period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    month_key, _sep, side = key.partition(":")
    month = _month_in(period, month_key)
    if month is None or side not in ("", "in", "out", OTHERS):
        return Transaction.objects.none()
    transactions = _transactions(month, filters)
    if side == "in":
        return transactions.filter(MONEY_IN)
    if side == "out":
        return transactions.filter(MONEY_OUT)
    if side == OTHERS:
        return _to_other_members(month, filters)
    return _all_money(month, filters)


def category_trends(period: Period, filters: Filters) -> ViewData:
    """Each Category's spending per month, biggest first, then Awaiting review. A line's key is its Category's
    key from Spending by Category; a point's adds ":<month>"."""
    spent = (
        _spending(period, filters)
        .annotate(month=TruncMonth("date"))
        .values("month", "subcategory__category")
        .annotate(total=-Sum("amount"))
    )
    by_line: dict[str, dict[str, Decimal]] = {}
    for s in spent:
        category = s["subcategory__category"]
        line = str(category) if category else AWAITING_REVIEW
        by_line.setdefault(line, {})[f"{s['month']:%Y-%m}"] = s["total"]
    months = _months_shown(period, {m for line in by_line.values() for m in line})

    def trend(label: str, key: str) -> Trend:
        return Trend(label, key, [by_line[key].get(_month_key(m), Decimal(0)) for m in months])

    rows = [
        trend(c.name, str(c.pk))
        for c in Category.objects.filter(kind=Category.Kind.SPENDING)
        if str(c.pk) in by_line
    ]
    rows.sort(key=lambda r: r.total, reverse=True)
    if AWAITING_REVIEW in by_line:
        rows.append(trend(_("Awaiting review"), AWAITING_REVIEW))
    chart = {
        "months": [_month_label(m) for m in months],
        "lines": [
            {
                "name": r.label,
                "key": r.key,
                "data": [float(a) for a in r.amounts],
                "keys": [f"{r.key}:{_month_key(m)}" for m in months],
            }
            for r in rows
        ],
    }
    return ViewData(rows, None, chart)


def trends_transactions(period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    line, _sep, month_key = key.partition(":")
    if month_key:
        month = _month_in(period, month_key)
        if month is None:
            return Transaction.objects.none()
        period = month
    return spending_transactions(period, filters, line)


def _buckets() -> tuple[dict[int, str], dict[str, str]]:
    """Each Account's Per Member bucket, its Member's key or the Joint one when several Members own it, and each
    bucket's label."""
    of_account, labels = {}, {}
    for account in Account.objects.prefetch_related("owners"):
        owners = list(account.owners.all())
        if len(owners) == 1:
            key = str(owners[0].pk)
            labels[key] = owners[0].get_full_name() or owners[0].get_username()
        else:
            key = JOINT
        of_account[account.pk] = key
    labels[JOINT] = _("Joint")
    return of_account, labels


def _bucket(key: str) -> list[int]:
    """The Accounts in one Per Member bucket."""
    of_account, _labels = _buckets()
    return [account for account, bucket in of_account.items() if bucket == key]


def filter_choices() -> tuple[list[tuple[str, str]], list[Account]]:
    """What the filter bar offers: each Per Member bucket's key and label, Members by name then Joint, and the
    Accounts that receive Statements."""
    of_account, labels = _buckets()
    keys = set(of_account.values())
    members = sorted((k for k in keys if k != JOINT), key=lambda k: labels[k].casefold())
    if JOINT in keys:
        members.append(JOINT)
    accounts = [a for a in Account.objects.all() if a.receives_statements]
    return [(k, labels[k]) for k in members], accounts


def per_member(period: Period, filters: Filters) -> ViewData:
    """Spending per Member, each split by Category, with the joint Accounts' spending in a Joint bucket of its
    own rather than shared out. A Member's key drills into their spending; with ":<Category key>", one segment.
    It compares every Member, so it ignores the Member filter."""
    filters = replace(filters, member=None)
    of_account, labels = _buckets()
    spent = (
        _spending(period, filters)
        .values("account", "subcategory__category")
        .annotate(total=-Sum("amount"))
    )
    by_bucket: dict[str, dict[str, Decimal]] = {}
    for s in spent:
        category = s["subcategory__category"]
        segment = str(category) if category else AWAITING_REVIEW
        bucket = by_bucket.setdefault(of_account[s["account"]], {})
        bucket[segment] = bucket.get(segment, Decimal(0)) + s["total"]
    segments = [
        (str(c.pk), c.name) for c in Category.objects.filter(kind=Category.Kind.SPENDING)
    ] + [(AWAITING_REVIEW, _("Awaiting review"))]
    members = sorted((k for k in by_bucket if k != JOINT), key=lambda k: labels[k].casefold())
    if JOINT in by_bucket:
        members.append(JOINT)
    rows = []
    for member in members:
        children = [
            Row(label, by_bucket[member][key], f"{member}:{key}")
            for key, label in segments
            if key in by_bucket[member]
        ]
        rows.append(
            Row(labels[member], sum((c.amount for c in children), Decimal(0)), member, children)
        )
    chart = {
        "members": [r.label for r in rows],
        "segments": [
            {
                "name": label,
                "key": key,
                "data": [
                    {
                        "value": float(by_bucket[m].get(key, Decimal(0))),
                        "key": f"{m}:{key}",
                    }
                    for m in members
                ],
            }
            for key, label in segments
            if any(key in by_bucket[m] for m in members)
        ],
    }
    return ViewData(rows, sum((r.amount for r in rows), Decimal(0)), chart)


def per_member_transactions(period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    filters = replace(filters, member=None)
    member, _sep, segment = key.partition(":")
    spending = _spending(period, filters).filter(account__in=_bucket(member))
    if not segment:
        return spending
    return spending & spending_transactions(period, filters, segment)


# Money flow's node keys besides Categories' and income Subcategories'.
INCOME = "in"
HOUSEHOLD = "household"


def _income(period: Period, filters: Filters) -> QuerySet[Transaction]:
    return _transactions(period, filters).filter(MONEY_IN)


def money_flow(period: Period, filters: Filters) -> ViewData:
    """A Sankey from income, per income Subcategory, through the Household to the Categories of Spending by
    Category, balanced by what was saved or drawn from savings. Unresolved money in is "Income awaiting review",
    as the node names must be unique. Only positive flows are drawn."""
    # None is the unresolved money in.
    received: dict[int | None, Decimal] = {
        r["subcategory"]: r["total"]
        for r in _income(period, filters).values("subcategory").annotate(total=Sum("amount"))
    }
    sources = [
        Row(s.name, received[s.pk], f"{INCOME}:{s.pk}")
        for s in Subcategory.objects.filter(category__kind=Category.Kind.INCOME).order_by(
            "category__position", "category", "is_catch_all", "position", "id"
        )
        if s.pk in received
    ]
    if None in received:
        sources.append(
            Row(_("Income awaiting review"), received[None], f"{INCOME}:{AWAITING_REVIEW}")
        )
    spending = spending_by_category(period, filters)
    sinks = [Row(r.label, r.amount, r.key) for r in spending.rows]
    money_in = sum((r.amount for r in sources), Decimal(0))
    rows = [
        Row(_("Money in"), money_in, INCOME, sources),
        Row(_("Money out"), spending.total, "out", sinks),
    ]
    # Under a Member filter, Transfers to or from other Members, as one node on whichever side they net to.
    others = Decimal(0)
    if filters.member:
        others = _to_other_members(period, filters).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal(0)
        rows.append(Row(_("To/from other Members"), others, OTHERS))
    saved = money_in + others - spending.total
    balance = Row(_("Saved") if saved >= 0 else _("From savings"), abs(saved), None)

    nodes = [{"name": r.key, "label": r.label, "key": r.key} for r in sources]
    nodes.append({"name": HOUSEHOLD, "label": _("Household"), "key": HOUSEHOLD})
    nodes += [{"name": r.key, "label": r.label, "key": r.key} for r in sinks]
    nodes.append({"name": OTHERS, "label": _("To/from other Members"), "key": OTHERS})
    # Only positive flows can be drawn, so the drawn balance can differ from the table's when a Category nets
    # to a Refund or an income Subcategory to a reversal.
    flows: list[tuple[str | None, str | None, Decimal]] = [
        (r.key, HOUSEHOLD, r.amount) for r in sources if r.amount > 0
    ]
    flows += [(HOUSEHOLD, r.key, r.amount) for r in sinks if r.amount > 0]
    if others > 0:
        flows.append((OTHERS, HOUSEHOLD, others))
    elif others < 0:
        flows.append((HOUSEHOLD, OTHERS, -others))
    drawn = sum((a for s, _t, a in flows if s != HOUSEHOLD), Decimal(0)) - sum(
        (a for s, _t, a in flows if s == HOUSEHOLD), Decimal(0)
    )
    if drawn:
        name = "saved" if drawn > 0 else "from_savings"
        label = _("Saved") if drawn > 0 else _("From savings")
        nodes.append({"name": name, "label": label, "key": None})
        flows.append((HOUSEHOLD, name, drawn) if drawn > 0 else (name, HOUSEHOLD, -drawn))
    links = [
        {"source": source, "target": target, "value": float(amount)}
        for source, target, amount in flows
    ]
    linked = {link["source"] for link in links} | {link["target"] for link in links}
    chart = {"nodes": [n for n in nodes if n["name"] in linked], "links": links}
    return ViewData(rows, balance, chart)


def money_flow_transactions(period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    """A node's Transactions: an income Subcategory's ("in:<id>", or "in:awaiting"), a Category's as in Spending
    by Category, all money in ("in"), all money out ("out"), what Transfers moved to or from other Members
    ("others") or all of it ("household")."""
    if key == HOUSEHOLD:
        return _all_money(period, filters)
    if key == OTHERS:
        return _to_other_members(period, filters)
    if key == INCOME:
        return _income(period, filters)
    if key == "out":
        return _spending(period, filters)
    group, _sep, source = key.partition(":")
    if group != INCOME:
        return spending_transactions(period, filters, key)
    income = _income(period, filters)
    if source == AWAITING_REVIEW:
        return income & Transaction.objects.unresolved()
    if source.isdigit():
        return income.filter(subcategory=int(source))
    return income.none()


def this_month() -> Flow:
    """The sidebar's figures: money in against money out in the month so far."""
    now = periods.today()
    sums = _transactions(Period.month(now.year, now.month), Filters()).aggregate(
        money_in=Sum("amount", filter=MONEY_IN), money_out=-Sum("amount", filter=MONEY_OUT)
    )
    return Flow(
        _("This month"),
        None,
        sums["money_in"] or Decimal(0),
        sums["money_out"] or Decimal(0),
    )


VIEWS = {
    "spending": spending_by_category,
    "cashflow": cashflow,
    "trends": category_trends,
    "per_member": per_member,
    "money_flow": money_flow,
}
DRILL_DOWNS = {
    "spending": spending_transactions,
    "cashflow": cashflow_transactions,
    "trends": trends_transactions,
    "per_member": per_member_transactions,
    "money_flow": money_flow_transactions,
}


def view_data(view: str, period: Period, filters: Filters) -> ViewData:
    return VIEWS[view](period, filters)


def drill_down(view: str, period: Period, filters: Filters, key: str) -> QuerySet[Transaction]:
    return DRILL_DOWNS[view](period, filters, key)
