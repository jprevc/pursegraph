"""PROTOTYPE (#75 Period completeness), throwaway: lives only on prototype/75-completeness."""

from django import template

register = template.Library()


@register.filter
def at(items, index):
    """`items[index]`, or None past its end."""
    try:
        return items[index]
    except (IndexError, KeyError, TypeError):
        return None


@register.filter
def month_state(completeness, key):
    return completeness.month(key) if completeness and key else "complete"


@register.filter
def tracked_from(pair):
    from dashboard.completeness import tracked_from_label

    return tracked_from_label(*pair)
