"""The parser module: turns a Statement file's content into a ParsedStatement.

`parse()` is the only entry point. It either returns the whole parsed Statement or raises
ParseError; it never returns a partial result, and anything it doesn't recognise is an error.
"""

from django.utils.translation import gettext as _

from .types import ParsedRow, ParsedStatement, ParseError, PrintedTotals

__all__ = ["parse", "ParsedRow", "ParsedStatement", "ParseError", "PrintedTotals"]


def parse(content: bytes, format: str) -> ParsedStatement:
    """Parse a Statement file. `format` is "csv" or "pdf"."""
    if format == "csv":
        from . import revolut_csv

        return revolut_csv.parse(content)
    raise ParseError(_("PDF Statements can't be imported yet."))
