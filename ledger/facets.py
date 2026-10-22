"""The Transactions page's facets (docs/design/transactions-page.md): what is chosen, read from and written to the
query string, the Transactions it narrows to, and how many each facet option would give with the others held."""

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import cached_property

from django.db.models import Count, Min, Q, QuerySet, Sum
from django.db.models.functions import TruncMonth
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from dashboard import periods
from dashboard.periods import Period
from dashboard.queries import VIEWS, Filters, buckets, filter_choices
from dashboard.templatetags.hues import hue
from pursegraph import figures

from .models import SOURCE_CAPTIONS, Category, Source, Transaction

UNRESOLVED = "unresolved"
TRANSFER = "transfer"
# What the Decided facet offers, in its order; "by import" (a bank fee) is left to Any way.
SOURCES = [Source.RULE, Source.LLM, Source.IBAN, Source.PAIRING, Source.MANUAL]
OUT, IN = "out", "in"


def _outcome(value: str) -> str:
    """`outcome` as the query names it, "unresolved", "transfer", "category-<id>" or "subcategory-<id>"; "" for
    anything else."""
    return (
        value
        if value in (UNRESOLVED, TRANSFER) or re.fullmatch(r"(sub)?category-\d+", value)
        else ""
    )


def _amount(value: str) -> Decimal | None:
    """An amount typed either way, "10,5" or "10.5", as a size; None if it can't be read."""
    try:
        amount = abs(Decimal(value.strip().replace(",", ".")))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _ids(value: str) -> tuple[int, ...]:
    """A comma-separated list of ids; none if any isn't one."""
    ids = [part for part in value.split(",") if part]
    return tuple(int(part) for part in ids) if all(part.isdigit() for part in ids) else ()


@dataclass(frozen=True)
class Choice:
    """What is chosen: a `period` (None for all time), the Dashboard's `filters` (a Member's bucket, Accounts), an
    `outcome`, a `source` (what decided it), a direction (`out` or `in`), an amount range of sizes, a search `q`,
    and the Transactions the Review queue `decided` just now ("See them in Transactions")."""

    period: Period | None = None
    filters: Filters = Filters()
    outcome: str = ""
    source: str = ""
    direction: str = ""
    least: Decimal | None = None
    most: Decimal | None = None
    q: str = ""
    decided: tuple[int, ...] = ()
    # Carried along untouched: the Dashboard's period and filters for the sidebar's links (`dashboard`), and the
    # Dashboard view and chart mark a drill-down's link came from, for the breadcrumb back (`from`, `mark`).
    dashboard: str = ""
    view: str = ""
    mark: str = ""
    # Each Account's Per Member bucket, looked up once.
    bucket_of_account: dict[int, str] = field(
        default_factory=lambda: buckets()[0], compare=False, repr=False
    )

    @classmethod
    def from_query(cls, params) -> "Choice":
        """The choice a request's query names; whatever can't be read is left unchosen."""
        period = Period.from_query(params) if params.get("period") or params.get("from") else None
        source = params.get("source", "")
        view = params.get("from", "")
        direction = params.get("dir", "")
        of_account, _labels = buckets()
        return cls(
            period=period,
            filters=Filters.from_query(params, of_account),
            outcome=_outcome(params.get("outcome", "")),
            source=source if source in SOURCES else "",
            direction=direction if direction in (OUT, IN) else "",
            least=_amount(params.get("min", "")),
            most=_amount(params.get("max", "")),
            q=params.get("q", "").strip(),
            decided=_ids(params.get("decided", "")),
            dashboard=params.get("dashboard", ""),
            view=view if view in VIEWS else "",
            mark=params.get("mark", "") if view in VIEWS else "",
            bucket_of_account=of_account,
        )

    @property
    def params(self) -> list[tuple[str, str]]:
        """The query parameters that name this choice."""
        named = [
            ("period", self.period.token if self.period else ""),
            *self.filters.params,
            ("outcome", self.outcome),
            ("source", self.source),
            ("dir", self.direction),
            ("min", "" if self.least is None else str(self.least)),
            ("max", "" if self.most is None else str(self.most)),
            ("q", self.q),
            ("decided", ",".join(map(str, self.decided))),
            ("dashboard", self.dashboard),
            ("from", self.view),
            ("mark", self.mark if self.view else ""),
        ]
        return [(name, value) for name, value in named if value]

    def changed(self, **changes) -> "Choice":
        """This choice with `changes`: fields, or a `member` or a single `account` (None for all of them). Changing
        the period, the Member or the outcome leaves the Dashboard mark the page was opened on."""
        filters = self.filters
        if "member" in changes:
            filters = replace(filters, member=changes.pop("member"))
        if "account" in changes:
            account = changes.pop("account")
            filters = replace(filters, accounts=frozenset([account] if account else []))
        if {"period", "outcome"} & changes.keys() or filters.member != self.filters.member:
            changes.update(view="", mark="")
        return replace(self, filters=filters, **changes)

    def query(self, **changes) -> str:
        """The query string of this choice with `changes` (see `changed`)."""
        return urlencode(self.changed(**changes).params)

    @cached_property
    def _facets(self) -> dict[str, Q]:
        """Each facet's condition."""
        member = self.filters.member
        return {
            "period": (
                Q(date__gte=self.period.start, date__lte=self.period.end) if self.period else Q()
            ),
            "member": (
                Q(account__in=[a for a, b in self.bucket_of_account.items() if b == member])
                if member
                else Q()
            ),
            "account": Filters(accounts=self.filters.accounts).scope(),
            "outcome": _outcome_condition(self.outcome),
            "source": Q(source=self.source) if self.source else Q(),
        }

    def condition(self, without: str = "") -> Q:
        """The chosen Transactions; `without` one facet, to count its options with the others held."""
        q = Q()
        for name, condition in self._facets.items():
            if name != without:
                q &= condition
        if self.direction:
            q &= Q(amount__lt=0) if self.direction == OUT else Q(amount__gt=0)
        if self.least is not None:
            q &= Q(amount__lte=-self.least) | Q(amount__gte=self.least)
        if self.most is not None:
            q &= Q(amount__gte=-self.most, amount__lte=self.most)
        if self.q:
            q &= (
                Q(description__unaccent__icontains=self.q)
                | Q(counterparty_name__unaccent__icontains=self.q)
                | Q(reference__unaccent__icontains=self.q)
            )
        if self.decided:
            q &= Q(pk__in=self.decided)
        return q


def _outcome_condition(outcome: str) -> Q:
    if outcome == UNRESOLVED:
        return Q(subcategory__isnull=True, is_transfer=False)
    if outcome == TRANSFER:
        return Q(is_transfer=True)
    kind, _sep, pk = outcome.partition("-")
    if kind == "category":
        return Q(subcategory__category=int(pk))
    if kind == "subcategory":
        return Q(subcategory=int(pk))
    return Q()


def rows(choice: Choice) -> QuerySet[Transaction]:
    """The chosen Transactions, newest first."""
    return Transaction.objects.filter(choice.condition()).order_by("-date", "-id")


def _grouped(choice: Choice, facet: str, *fields, **expressions) -> list[dict]:
    """How many Transactions each combination of `fields` (and named `expressions`) has, with every facet but
    `facet` held."""
    return list(
        Transaction.objects.filter(choice.condition(without=facet))
        .values(*fields, **expressions)
        .annotate(n=Count("id"))
        .order_by()
    )


def counts(choice: Choice) -> dict[str, dict[str, int]]:
    """Per facet, how many Transactions each option would give with the other facets held, by the option's query
    value ("" for the facet's Any option). An option that gives none isn't listed. One query per facet."""
    result: dict[str, Counter[str]] = {}

    by_month = Counter[str]()
    for group in _grouped(choice, "period", month=TruncMonth("date")):
        by_month[f"{group['month']:%Y-%m}"] += group["n"]
        by_month[""] += group["n"]
    result["period"] = by_month

    by_member = Counter[str]()
    for group in _grouped(choice, "member", "account"):
        by_member[choice.bucket_of_account[group["account"]]] += group["n"]
        by_member[""] += group["n"]
    result["member"] = by_member

    by_account = Counter[str]()
    for group in _grouped(choice, "account", "account"):
        by_account[str(group["account"])] += group["n"]
        by_account[""] += group["n"]
    result["account"] = by_account

    by_outcome = Counter[str]()
    for group in _grouped(choice, "outcome", "subcategory", "subcategory__category", "is_transfer"):
        if group["subcategory"]:
            by_outcome[f"category-{group['subcategory__category']}"] += group["n"]
            by_outcome[f"subcategory-{group['subcategory']}"] += group["n"]
        else:
            by_outcome[TRANSFER if group["is_transfer"] else UNRESOLVED] += group["n"]
        by_outcome[""] += group["n"]
    result["outcome"] = by_outcome

    by_source = Counter[str]()
    for group in _grouped(choice, "source", "source"):
        if group["source"] in SOURCES:
            by_source[group["source"]] += group["n"]
        by_source[""] += group["n"]
    result["source"] = by_source

    return {facet: dict(options) for facet, options in result.items()}


@dataclass(frozen=True)
class Option:
    """One facet option: its `label`, its `count` with the other facets held, whether it is `chosen`, and the query
    value picking it submits (`pick`; "" picks nothing, which clears the facet). `dot` is "awaiting", "transfer" or
    a Category's hue token, `note` a line explaining it and `sub` marks a Subcategory under its Category."""

    label: str
    count: int
    chosen: bool
    pick: str
    dot: str = ""
    note: str = ""
    sub: bool = False
    # Where focus can find it again after a swap.
    key: str = ""


@dataclass(frozen=True)
class Group:
    """A facet's options, under `label`. `param` is the query parameter its options submit, and `carry` the rest
    of the choice, which they keep; `chosen` says the facet is set, so it offers Clear."""

    param: str
    label: str
    options: list[Option]
    carry: list[tuple[str, str]]
    chosen: bool

    @property
    def chosen_option(self) -> Option | None:
        """The option chosen, unless it is the Any one."""
        return next((o for o in self.options[1:] if o.chosen), None)


# The Decided facet's line on each source.
SOURCE_NOTES = {
    Source.RULE: gettext_lazy(
        "A Rule matched it. Rules are patterns a Member set up, often from a correction."
    ),
    Source.LLM: gettext_lazy("The local model suggested it, sure enough to take it on its own."),
    Source.IBAN: gettext_lazy(
        "The other side's IBAN is one of the Household's, so it's a Transfer."
    ),
    Source.PAIRING: gettext_lazy(
        "Matched with its other side in another of the Household's Accounts."
    ),
    Source.MANUAL: gettext_lazy("A Member chose it."),
}

# What clears each facet, as `Choice.changed` takes it.
CLEARED = {"period": None, "member": None, "account": None, "outcome": "", "source": ""}


def _options(
    values: list[tuple[str, str]], chosen: str, counts: dict[str, int], **extra
) -> list[Option]:
    """Options from (value, label) pairs; picking the chosen one again clears the facet."""
    return [
        Option(
            label,
            counts.get(value, 0),
            value == chosen,
            "" if value == chosen else value,
            key=value,
            **extra,
        )
        for value, label in values
    ]


def _months(first: date | None) -> list[tuple[str, str]]:
    """Each month from the one holding `first` to this one, newest first, as (token, label); this one is "(so far)"."""
    this_month = periods.today().replace(day=1)
    months = []
    month = this_month
    while first and month >= first.replace(day=1):
        label = figures.month(month)
        if month == this_month:
            label = _("%(month)s (so far)") % {"month": label}
        months.append((f"{month:%Y-%m}", label))
        month = (month - timedelta(days=1)).replace(day=1)
    return months


def rail(choice: Choice, counts: dict[str, dict[str, int]], total: int) -> list[Group]:
    """The facet rail: Period, Member, Account, Outcome and Decided, each option counted with the other facets held.
    `total` is how many Transactions the choice gives, the count of a chosen period the months don't name."""
    members, accounts = filter_choices()
    first = Transaction.objects.aggregate(first=Min("date"))["first"]

    def group(param: str, label: str, any_label: str, options: list[Option], chosen: bool) -> Group:
        any_option = Option(any_label, counts[param].get("", 0), not chosen, "", key="any")
        carry = choice.changed(**{param: CLEARED[param]}).params
        return Group(param, label, [any_option, *options], carry, chosen)

    # Period: All time, then each month newest first, and a chosen period of another unit on top.
    months = _months(first)
    token = choice.period.token if choice.period else ""
    period_options = _options(months, token, counts["period"])
    if choice.period and token not in dict(months):
        period_options.insert(0, Option(choice.period.label, total, True, "", key=token))

    accounts_chosen = choice.filters.accounts
    account_options = _options(
        [(str(a.pk), a.name) for a in accounts],
        str(next(iter(accounts_chosen))) if len(accounts_chosen) == 1 else "",
        counts["account"],
    )

    outcome_options = [
        *_options(
            [(UNRESOLVED, _("Awaiting review"))], choice.outcome, counts["outcome"], dot="awaiting"
        ),
        *_options([(TRANSFER, _("Transfer"))], choice.outcome, counts["outcome"], dot="transfer"),
    ]
    for category in Category.objects.prefetch_related("subcategories"):
        value = f"category-{category.pk}"
        subcategories = [(f"subcategory-{s.pk}", s.name) for s in category.subcategories.all()]
        opened = choice.outcome == value or choice.outcome in dict(subcategories)
        outcome_options += _options(
            [(value, category.name)], choice.outcome, counts["outcome"], dot=hue(category.pk)
        )
        if opened:
            # Picking the chosen Subcategory again goes back to its Category.
            outcome_options += [
                replace(o, pick=value if o.chosen else o.pick, sub=True)
                for o in _options(subcategories, choice.outcome, counts["outcome"])
            ]

    source_options = [
        replace(o, note=str(SOURCE_NOTES[Source(o.key)]))
        for o in _options(
            [(s.value, str(SOURCE_CAPTIONS[s])) for s in SOURCES], choice.source, counts["source"]
        )
    ]

    return [
        group("period", _("Period"), _("All time"), period_options, choice.period is not None),
        group(
            "member",
            _("Member"),
            _("Everyone"),
            _options(members, choice.filters.member or "", counts["member"]),
            bool(choice.filters.member),
        ),
        group("account", _("Account"), _("All Accounts"), account_options, bool(accounts_chosen)),
        group("outcome", _("Outcome"), _("Any outcome"), outcome_options, bool(choice.outcome)),
        group("source", _("Decided"), _("Any way"), source_options, bool(choice.source)),
    ]


def named(choice: Choice, groups: list[Group]) -> list[str]:
    """The filters set, as the summary line names them: "September 2026", "Food › Groceries", "Out"."""
    names = []
    for group in groups:
        chosen = group.chosen_option
        if chosen and chosen.sub:
            category = next(
                o for o in reversed(group.options[: group.options.index(chosen)]) if not o.sub
            )
            names.append(f"{category.label} › {chosen.label}")
        elif chosen:
            names.append(chosen.label)
        elif group.param == "account" and choice.filters.accounts:
            count = len(choice.filters.accounts)
            names.append(
                ngettext("%(count)d Account", "%(count)d Accounts", count) % {"count": count}
            )
    if choice.direction:
        names.append(str(_("Out") if choice.direction == OUT else _("In")))
    least = figures.money(choice.least) if choice.least is not None else ""
    most = figures.money(choice.most) if choice.most is not None else ""
    if least and most:
        names.append(_("%(least)s to %(most)s") % {"least": least, "most": most})
    elif least:
        names.append(_("%(least)s or more") % {"least": least})
    elif most:
        names.append(_("up to %(most)s") % {"most": most})
    if choice.decided:
        count = len(choice.decided)
        names.append(_("Decided just now · %(count)d") % {"count": count})
    return names


def totals(choice: Choice) -> tuple[int, Decimal, Decimal]:
    """How many Transactions the choice gives, and their money out and in, Transfers left aside as the Dashboard
    leaves them."""
    moved = Q(is_transfer=False)
    result = Transaction.objects.filter(choice.condition()).aggregate(
        count=Count("id"),
        out=Sum("amount", filter=moved & Q(amount__lt=0), default=Decimal(0)),
        money_in=Sum("amount", filter=moved & Q(amount__gt=0), default=Decimal(0)),
    )
    return result["count"], abs(result["out"]), result["money_in"]
