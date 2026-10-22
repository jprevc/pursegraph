"""What an import tells the Member (docs/design/import.md, Import copy): its domain counts and its banner."""

from datetime import date

from ledger.import_results import banner, domain_counts
from ledger.importer import FileResult, ImportRejected, ImportSummary
from ledger.models import Account


def summary(**counts):
    defaults = dict.fromkeys(
        (
            "imported_count",
            "duplicate_count",
            "skipped_count",
            "rule_count",
            "paired_count",
            "one_sided_count",
            "converted_count",
            "ambiguous_count",
            "awaiting_count",
        ),
        0,
    )
    return ImportSummary(
        account=Account(name="Luka's N26"),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        **(defaults | counts),
    )


def said(counts):
    return [f"{c.figure} {c.text}" for c in counts]


def test_every_count_that_applies_is_said():
    counts = domain_counts(
        summary(
            imported_count=64,
            duplicate_count=22,
            skipped_count=4,
            paired_count=2,
            one_sided_count=1,
            converted_count=1,
            ambiguous_count=1,
            rule_count=41,
            awaiting_count=20,
        )
    )

    assert said(counts) == [
        "64 Transactions imported",
        "22 Duplicates skipped: already imported from an earlier Statement",
        "4 card payments still pending or declined, left out",
        "3 Transfers recognised: 2 paired, 1 one-sided",
        "1 categorized Transaction is now a Transfer",
        "1 Transfer has several possible other sides, so it waits in the Review queue",
        "41 categorized by Rules",
        "20 wait for suggestions and review",
    ]
    assert not any(c.zero for c in counts)


def test_zero_counts_read_no_and_the_ones_that_only_sometimes_apply_are_left_out():
    counts = domain_counts(summary(imported_count=1))

    assert said(counts) == [
        "1 Transaction imported",
        "No Duplicates",
        "No Transfers",
        "None categorized by Rules",
        "None wait for suggestions and review",
    ]
    assert [c.zero for c in counts] == [False, True, True, True, True]


def rejected(filename, *, already=False):
    return FileResult(
        filename, rejection=ImportRejected("…", heading="…", already_imported=already)
    )


def test_the_banner_names_what_was_imported_and_what_is_left():
    said = banner(
        [
            FileResult("a.pdf", summary=summary(imported_count=100, awaiting_count=30)),
            FileResult("b.pdf", summary=summary(imported_count=73, awaiting_count=14)),
            rejected("c.pdf"),
            rejected("d.pdf"),
            rejected("e.pdf", already=True),
        ],
        needs_account=1,
    )

    assert said.headline == "173 Transactions imported from 2 files"
    assert said.rest == (
        "44 wait for review · 1 file needs an Account · 2 files weren't imported · 1 was already imported"
    )
    assert said.to_review == 44
    assert said.imported


def test_with_nothing_imported_the_banner_says_so():
    said = banner([rejected("a.pdf", already=True)], needs_account=0)

    assert said.headline == "Nothing imported"
    assert said.rest == "1 was already imported"
    assert said.to_review == 0
    assert not said.imported
