"""`{% load matched %}`, then `{{ t.description|matched:rule.description_contains }}`: the text a Rule matched,
in a soft highlight."""

from django import template
from django.utils.html import format_html

from ledger.rules import matched_span

register = template.Library()


@register.filter
def matched(description: str, contains: str) -> str:
    span = matched_span(description, contains or "")
    if span is None:
        return description
    start, end = span
    return format_html(
        "{}<mark>{}</mark>{}", description[:start], description[start:end], description[end:]
    )
