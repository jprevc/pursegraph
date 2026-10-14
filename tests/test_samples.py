"""Local-only and opt-in (`PURSEGRAPH_SAMPLES=1`): the parsers against the real Statements in the
gitignored `samples/`.

Only the checks the importer runs are asserted, so no real data is written into the tests.
"""

import os
from decimal import Decimal
from pathlib import Path

import pytest

from ledger.parsers import ParseError, parse

SAMPLES = Path(__file__).parent.parent / "samples"
PDFS = sorted(SAMPLES.glob("*.pdf")) if os.environ.get("PURSEGRAPH_SAMPLES") else []


@pytest.mark.skipif(not PDFS, reason="set PURSEGRAPH_SAMPLES=1 and put Statements in samples/")
@pytest.mark.parametrize("path", PDFS, ids=lambda path: path.name)
def test_sample_pdf_adds_up(path):
    try:
        statement = parse(path.read_bytes(), "pdf")
    except ParseError as error:
        if "not a Statement of a supported bank" in str(error):
            pytest.skip("no parser for this bank yet")
        raise

    rows, totals = statement.rows, statement.printed_totals
    assert statement.opening_balance + sum(r.amount for r in rows) == statement.closing_balance
    assert totals is not None  # every supported PDF prints its totals
    assert totals.count_in in (None, sum(1 for r in rows if r.amount > 0))
    assert totals.count_out in (None, sum(1 for r in rows if r.amount < 0))
    assert totals.money_in == sum((r.amount for r in rows if r.amount > 0), Decimal(0))
    assert totals.money_out == -sum((r.amount for r in rows if r.amount < 0), Decimal(0))
