"""Template filters for the Dashboard's colour and proportions: `{% load hues %}`, then
`style="--hue: var(--{{ key|hue }})"` and `{{ amount|ratio:total|share }}`."""

from decimal import Decimal

from django import template

from dashboard.queries import AWAITING_REVIEW

register = template.Library()


@register.filter
def hue(key) -> str:
    """The colour token a chart mark's key wears (DESIGN.md, the Fixed Hue Rule): a Category's `cat-((id − 1) mod
    10)`, whatever its rank, and Awaiting review's neutral grey; "" for any other key."""
    key = str(key)
    if key == AWAITING_REVIEW:
        return "awaiting"
    return f"cat-{(int(key) - 1) % 10}" if key.isdigit() else ""


@register.filter
def ratio(part, whole) -> Decimal:
    """`part` as a fraction of `whole`, never below 0 (a Category that nets to a Refund draws no bar), and 0 of
    nothing."""
    whole = Decimal(str(whole or 0))
    if not whole:
        return Decimal(0)
    return max(Decimal(str(part)) / whole, Decimal(0))
