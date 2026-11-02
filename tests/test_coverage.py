"""Coverage and its Gaps (CONTEXT.md): the days between an Account's Statements, and those since its last one; and
what deleting a Statement leaves."""

from datetime import date

from ledger.coverage import DateRange, Shrink, gaps, removing

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


JULY = DateRange(date(2026, 7, 1), date(2026, 7, 31))
TODAY = date(2026, 10, 17)


def days(start, end):
    return DateRange(date(2026, *start), date(2026, *end))


def test_removing_a_statement_between_others_leaves_a_gap():
    assert removing(JULY, [JUNE, AUGUST], until=TODAY) == Shrink(gaps=[JULY], untracked=[])


def test_removing_the_last_statement_leaves_a_gap_up_to_today():
    assert removing(AUGUST, [JUNE, JULY], until=TODAY) == Shrink(gaps=[AUGUST], untracked=[])


def test_the_days_another_statement_still_covers_stay_covered():
    assert removing(JULY, [JUNE, days((7, 20), (8, 31))], until=TODAY) == Shrink(
        gaps=[days((7, 1), (7, 19))], untracked=[]
    )
    assert removing(JULY, [days((6, 1), (8, 31))], until=TODAY) == Shrink(gaps=[], untracked=[])


def test_removing_the_first_statement_makes_its_days_untracked_not_a_gap():
    assert removing(JUNE, [JULY], until=TODAY) == Shrink(gaps=[], untracked=[JUNE])
    assert removing(JUNE, [], until=TODAY) == Shrink(gaps=[], untracked=[JUNE])


def test_days_after_today_are_neither():
    assert removing(days((10, 1), (10, 31)), [AUGUST], until=TODAY) == Shrink(
        gaps=[days((10, 1), (10, 17))], untracked=[]
    )
