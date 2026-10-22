"""The Accounts board (docs/design/import.md): every Account's Coverage on one time axis, up to today."""

from datetime import date

from ledger.board import Axis, track
from ledger.coverage import DateRange

TODAY = date(2026, 10, 19)
JUNE = DateRange(date(2026, 6, 1), date(2026, 6, 30))
JULY = DateRange(date(2026, 7, 1), date(2026, 7, 31))
AUGUST = DateRange(date(2026, 8, 1), date(2026, 8, 31))
SEPTEMBER = DateRange(date(2026, 9, 1), date(2026, 9, 30))


def kinds(stretches):
    return [(s.kind, s.range) for s in stretches]


def test_a_track_is_its_covered_stretches_and_gaps_up_to_today():
    stretches = track(Axis(JUNE.start, TODAY), [JUNE, AUGUST], before=[JUNE, AUGUST])

    assert kinds(stretches) == [
        ("covered", JUNE),
        ("gap", JULY),
        ("covered", AUGUST),
        ("gap", DateRange(date(2026, 9, 1), TODAY)),
    ]
    assert [s.since_last_statement for s in stretches] == [False, False, False, True]


def test_the_stretch_this_import_added_is_new():
    stretches = track(
        Axis(JUNE.start, TODAY),
        [DateRange(JUNE.start, SEPTEMBER.end)],
        before=[DateRange(JUNE.start, AUGUST.end)],
    )

    assert kinds(stretches)[:2] == [
        ("covered", DateRange(JUNE.start, AUGUST.end)),
        ("new", SEPTEMBER),
    ]


def test_a_new_stretch_can_fill_a_gap_between_covered_ones():
    stretches = track(
        Axis(JUNE.start, TODAY), [DateRange(JUNE.start, AUGUST.end)], before=[JUNE, AUGUST]
    )

    assert kinds(stretches)[:3] == [("covered", JUNE), ("new", JULY), ("covered", AUGUST)]


def test_coverage_up_to_today_leaves_no_gap_since_the_last_statement():
    covered = DateRange(JUNE.start, TODAY)

    assert kinds(track(Axis(JUNE.start, TODAY), [covered], before=[covered])) == [
        ("covered", covered)
    ]


def test_stretches_are_placed_on_the_axis_up_to_the_end_of_today():
    axis = Axis(date(2026, 1, 1), date(2026, 1, 10))

    [first, gap] = track(axis, [DateRange(date(2026, 1, 1), date(2026, 1, 4))], before=[])

    assert (first.left, first.width) == (0, 40)
    assert (gap.left, gap.width) == (40, 60)


def test_a_gap_of_whole_months_is_labelled_by_its_months_else_by_its_days():
    axis = Axis(JUNE.start, TODAY)
    [_, july, _, since] = track(axis, [JUNE, AUGUST], before=[JUNE, AUGUST])
    [_, two_months, _, _] = track(axis, [JUNE, SEPTEMBER], before=[JUNE, SEPTEMBER])
    [_, partial, _, _] = track(
        axis, [JUNE, DateRange(date(2026, 7, 20), AUGUST.end)], before=[JUNE]
    )

    assert july.label == "Jul"
    assert two_months.label == "Jul–Aug"
    assert partial.label == "19 d"
    assert since.label == "49 d"


def test_the_axis_marks_quarters_and_names_the_year_at_january():
    axis = Axis(date(2025, 2, 10), TODAY)

    assert [(t.label, t.is_year) for t in axis.ticks()] == [
        ("Apr", False),
        ("Jul", False),
        ("Oct", False),
        ("2026", True),
        ("Apr", False),
        ("Jul", False),
        ("Oct", False),
    ]


def test_each_stretch_says_what_it_is():
    stretches = track(Axis(JUNE.start, TODAY), [JUNE, SEPTEMBER], before=[JUNE])

    assert [s.said for s in stretches] == [
        "Covered 1–30 Jun 2026",
        "Gap 1 Jul – 31 Aug 2026",
        "Covered by this import 1–30 Sep 2026",
        "Gap 1–19 Oct 2026, since the last Statement",
    ]


def test_a_statement_running_past_today_stops_at_the_end_of_the_axis():
    axis = Axis(date(2026, 1, 1), date(2026, 1, 10))

    [stretch] = track(axis, [DateRange(date(2026, 1, 6), date(2026, 1, 20))], before=[])

    assert (stretch.left, stretch.left + stretch.width) == (50, 100)
