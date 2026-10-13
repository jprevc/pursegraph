"""The PDF-to-text adapter in front of the PDF parsers: pdfplumber's plain `extract_text()`, page
after page, with no layout mode and no OCR. Tests stub `extract_text` to return fixture text."""

import io

import pdfplumber
from django.utils.translation import gettext as _
from pdfplumber.utils.exceptions import PdfminerException

from .types import ParseError


def extract_text(content: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except PdfminerException as err:
        raise ParseError(_("The file is not a readable PDF.")) from err
