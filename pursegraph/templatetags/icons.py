"""`{% load icons %}`, then `{% icon "left" %}`: a line icon from the sprite in `templates/_icons.html`."""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name: str) -> str:
    """The text beside it, or an `aria-label` on its control, names it."""
    return format_html(
        '<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>',
        name,
    )
