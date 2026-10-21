"""Template filters for figures: `{% load figures %}`, then `{{ amount|money }}`. See `pursegraph.figures`."""

from django import template

from pursegraph import figures

register = template.Library()

register.filter("money", figures.money)
register.filter("money_whole", figures.money_whole)
register.filter("money_signed", figures.money_signed)
register.filter("share", figures.share)
register.filter("day", figures.day)
register.filter("date_range", figures.date_range)
register.filter("month", figures.month)
