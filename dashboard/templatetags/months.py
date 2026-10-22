"""Template filters for the months of a view's table and how complete each is: `{% load months %}`, then
`{% with month=completeness|month_of:row.key %}`, or `{% for amount, month in row.amounts|beside:months %}` with
`months=completeness|months_of:chart.keys`."""

from django import template

from dashboard.completeness import Completeness, Month

register = template.Library()


@register.filter
def month_of(completeness: Completeness, key: str) -> Month | None:
    """The month a table row's key names."""
    return completeness.month(key)


@register.filter
def months_of(completeness: Completeness, keys: list[str]) -> list[Month | None]:
    """The months of a table's columns, from its chart's keys."""
    return completeness.months_of(keys)


@register.filter
def beside(values: list, months: list) -> list[tuple]:
    """Each value with its month."""
    return list(zip(values, months, strict=True))
