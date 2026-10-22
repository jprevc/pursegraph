"""Coverage and its Gaps (CONTEXT.md): the days between an Account's Statements, and those since its last one."""

from datetime import date

from ledger.coverage import DateRange, gaps

JUNE = DateRange(date(2026, 6, 1), date(2026, 6, 30))
AUGUST = DateRange(date(2026, 8, 1), date(2026, 8, 31))


def test_the_gaps_are_the_days_between_the_statements():
    assert gaps([JUNE, AUGUST]) == [DateRange(date(2026, 7, 1), date(2026, 7, 31))]


def test_up_to_a_day_the_gaps_include_the_stretch_since_the_last_statement():
    assert gaps([JUNE, AUGUST], until=date(2026, 10, 17)) == [
        DateRange(date(2026, 7, 1), date(2026, 7, 31)),
        DateRange(date(2026, 9, 1), date(2026, 10, 17)),
    ]


def test_a_coverage_reaching_the_day_has_no_gap_since_its_last_statement():
    assert gaps([JUNE, AUGUST], until=date(2026, 8, 31)) == [
        DateRange(date(2026, 7, 1), date(2026, 7, 31))
    ]
    assert gaps([JUNE, AUGUST], until=date(2026, 8, 20)) == [
        DateRange(date(2026, 7, 1), date(2026, 7, 31))
    ]


def test_no_coverage_has_no_gaps():
    assert gaps([], until=date(2026, 10, 17)) == []
