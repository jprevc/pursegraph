"""The parser module: turns a Statement file's content into a ParsedStatement.

`parse()` is the only entry point. It either returns the whole parsed Statement or raises
ParseError; it never returns a partial result, and anything it doesn't recognise is an error.
"""

from django.utils.translation import gettext as _

from .types import ParsedRow, ParsedStatement, ParseError, Totals

__all__ = ["parse", "parse_pdf_text", "ParsedRow", "ParsedStatement", "ParseError", "Totals"]


def parse(content: bytes, format: str) -> ParsedStatement:
    """Parse a Statement file. `format` is "csv" or "pdf"."""
    if format == "csv":
        from . import revolut_csv

        return revolut_csv.parse(content)
    from . import pdf_text

    return parse_pdf_text(pdf_text.extract_text(content))


def parse_pdf_text(text: str) -> ParsedStatement:
    """Parse a PDF Statement's extracted text, detecting the bank from it."""
    if "BANKA SPARKASSE" in text and "IZPISEK TRANSAKCIJSKEGA RAČUNA" in text:
        from . import sparkasse_pdf

        return sparkasse_pdf.parse(text)
    if "Bank Statement Nr." in text and "• BIC: NTSBDEB1" in text:
        from . import n26_pdf

        return n26_pdf.parse(text)
    raise ParseError(_("This PDF is not a Statement of a supported bank."))
