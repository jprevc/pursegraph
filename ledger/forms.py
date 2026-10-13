from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .importer import NewAccount
from .models import Account, Bank, Category, Source, Subcategory, Transaction

NEW = "new"


class ImportForm(forms.Form):
    """A Revolut CSV has no IBAN, so the Member picks the Account (or creates one) up front."""

    file = forms.FileField(label=_("Statement file"))
    account = forms.ChoiceField(label=_("Account"))
    new_account_name = forms.CharField(label=_("New Account name"), max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = Account.objects.filter(bank=Bank.REVOLUT)
        self.fields["account"].choices = [
            ("", _("Choose an Account")),
            *((str(a.pk), a.name) for a in accounts),
            (NEW, _("New Revolut Account")),
        ]
        # Preselect the only Revolut Account, or a new one when there is none.
        if len(accounts) == 1:
            self.initial["account"] = str(accounts[0].pk)
        elif not accounts:
            self.initial.update(account=NEW, new_account_name="Revolut")

    def clean(self):
        data = super().clean()
        if data.get("account") == NEW and not data.get("new_account_name", "").strip():
            self.add_error("new_account_name", _("Name the new Account."))
        return data

    def chosen_account(self) -> Account | NewAccount:
        if self.cleaned_data["account"] == NEW:
            return NewAccount(self.cleaned_data["new_account_name"].strip())
        return Account.objects.get(pk=self.cleaned_data["account"])


TRANSFER = "transfer"


class OutcomeForm(forms.Form):
    """A manual outcome: a Subcategory's id, or TRANSFER."""

    outcome = forms.ChoiceField(label=_("Outcome"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["outcome"].choices = [
            *((str(s.pk), s.name) for s in Subcategory.objects.all()),
            (TRANSFER, _("Transfer")),
        ]

    def save(self, transaction: Transaction) -> None:
        value = self.cleaned_data["outcome"]
        subcategory = None if value == TRANSFER else Subcategory.objects.get(pk=value)
        transaction.set_outcome(subcategory, source=Source.MANUAL)

class TransactionFilterForm(forms.Form):
    """The Transactions view's search and filters, from the query string."""

    q = forms.CharField(label=_("Search"), required=False)
    account = forms.ModelChoiceField(
        label=_("Account"), queryset=Account.objects.all(), required=False, empty_label=_("All Accounts"),
    )
    # "unresolved", "transfer", "category-<id>" or "subcategory-<id>".
    outcome = forms.ChoiceField(label=_("Outcome"), required=False)

    def __init__(self, *args, categories, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["outcome"].choices = [
            ("", _("All outcomes")),
            ("unresolved", _("Awaiting review")),
            (TRANSFER, _("Transfer")),
            *(
                (category.name, [
                    (f"category-{category.pk}", _("All of %(category)s") % {"category": category.name}),
                    *((f"subcategory-{s.pk}", s.name) for s in category.subcategories.all()),
                ])
                for category in categories
            ),
        ]

    def filter(self, transactions):
        if not self.is_valid():
            return transactions.none()
        data = self.cleaned_data
        if q := data["q"].strip():
            transactions = transactions.filter(
                Q(description__unaccent__icontains=q) | Q(counterparty_name__unaccent__icontains=q)
                | Q(reference__unaccent__icontains=q)
            )
        if data["account"]:
            transactions = transactions.filter(account=data["account"])
        outcome = data["outcome"]
        if outcome == "unresolved":
            transactions = transactions.unresolved()
        elif outcome == TRANSFER:
            transactions = transactions.filter(is_transfer=True)
        elif outcome.startswith("category-"):
            transactions = transactions.filter(subcategory__category=outcome.removeprefix("category-"))
        elif outcome.startswith("subcategory-"):
            transactions = transactions.filter(subcategory=outcome.removeprefix("subcategory-"))
        return transactions


class CategoryForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=100, error_messages={"required": _("Name the Category.")})
    kind = forms.ChoiceField(label=_("Kind"), choices=Category.Kind.choices)


class NameForm(forms.Form):
    """Renames a Category, or names or renames a Subcategory."""

    name = forms.CharField(label=_("Name"), max_length=100, error_messages={"required": _("Give it a name.")})
