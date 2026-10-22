"""What an import tells the Member (docs/design/import.md, Import copy): the banner over the board, and each
Statement's domain counts."""

from dataclasses import dataclass

from django.utils.formats import number_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .importer import FileResult, ImportSummary


@dataclass(frozen=True)
class Count:
    """One line of the domain counts: a figure ("64", or "No" for none) and what it counts."""

    figure: str
    text: str
    zero: bool = False
    links_review: bool = False
    """Followed by a link to the Review queue."""


def domain_counts(summary: ImportSummary) -> list[Count]:
    """The counts of one imported Statement. Zero reads "No …"; a count that only sometimes applies is left out."""
    s = summary
    transfers = s.paired_count + s.one_sided_count

    def count(n: int, text: str) -> Count:
        return Count(number_format(n, force_grouping=True), text)

    counts = [
        count(
            s.imported_count,
            ngettext("Transaction imported", "Transactions imported", s.imported_count),
        ),
        count(
            s.duplicate_count,
            ngettext(
                "Duplicate skipped: already imported from an earlier Statement",
                "Duplicates skipped: already imported from an earlier Statement",
                s.duplicate_count,
            ),
        )
        if s.duplicate_count
        else Count(_("No"), _("Duplicates"), zero=True),
    ]
    if s.skipped_count:
        counts.append(
            count(
                s.skipped_count,
                ngettext(
                    "card payment still pending or declined, left out",
                    "card payments still pending or declined, left out",
                    s.skipped_count,
                ),
            )
        )
    counts.append(
        count(
            transfers,
            ngettext(
                "Transfer recognised: %(paired)s paired, %(one_sided)s one-sided",
                "Transfers recognised: %(paired)s paired, %(one_sided)s one-sided",
                transfers,
            )
            % {"paired": s.paired_count, "one_sided": s.one_sided_count},
        )
        if transfers
        else Count(_("No"), _("Transfers"), zero=True)
    )
    if s.converted_count:
        counts.append(
            count(
                s.converted_count,
                ngettext(
                    "categorized Transaction is now a Transfer",
                    "categorized Transactions are now Transfers",
                    s.converted_count,
                ),
            )
        )
    if s.ambiguous_count:
        counts.append(
            count(
                s.ambiguous_count,
                ngettext(
                    "Transfer has several possible other sides, so it waits in the Review queue",
                    "Transfers have several possible other sides, so they wait in the Review queue",
                    s.ambiguous_count,
                ),
            )
        )
    counts.append(
        count(s.rule_count, _("categorized by Rules"))
        if s.rule_count
        else Count(_("No"), _("Transactions categorized by Rules"), zero=True)
    )
    counts.append(
        Count(
            number_format(s.awaiting_count, force_grouping=True),
            ngettext(
                "waits for suggestions and review",
                "wait for suggestions and review",
                s.awaiting_count,
            ),
            links_review=True,
        )
        if s.awaiting_count
        else Count(_("No"), _("Transactions wait for suggestions and review"), zero=True)
    )
    return counts


@dataclass(frozen=True)
class Banner:
    """The result of an import, as the banner over the board says it."""

    headline: str
    rest: str
    """What waits for the Member: review, files needing an Account, files not imported or already imported."""
    to_review: int
    imported: bool
    """Whether any file was imported."""


def banner(results: list[FileResult], *, needs_account: int) -> Banner:
    summaries = [r.summary for r in results if r.summary]
    rejections = [r.rejection for r in results if r.rejection]
    already = sum(r.already_imported for r in rejections)
    not_imported = len(rejections) - already
    imported = sum(s.imported_count for s in summaries)
    to_review = sum(s.awaiting_count for s in summaries)
    if summaries:
        # Two counts, each with its own plural.
        headline = _("%(transactions)s %(files)s") % {
            "transactions": ngettext(
                "%(count)s Transaction imported", "%(count)s Transactions imported", imported
            )
            % {"count": number_format(imported, force_grouping=True)},
            "files": ngettext("from %(count)s file", "from %(count)s files", len(summaries))
            % {"count": len(summaries)},
        }
    else:
        headline = _("Nothing imported")
    rest = [
        ngettext("%(count)s waits for review", "%(count)s wait for review", to_review)
        % {"count": number_format(to_review, force_grouping=True)}
        if to_review
        else "",
        ngettext(
            "%(count)s file needs an Account", "%(count)s files need an Account", needs_account
        )
        % {"count": needs_account}
        if needs_account
        else "",
        ngettext("%(count)s file wasn't imported", "%(count)s files weren't imported", not_imported)
        % {"count": not_imported}
        if not_imported
        else "",
        ngettext("%(count)s was already imported", "%(count)s were already imported", already)
        % {"count": already}
        if already
        else "",
    ]
    return Banner(
        headline, _(" · ").join(part for part in rest if part), to_review, bool(summaries)
    )
