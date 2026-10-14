import base64
import binascii
from typing import cast

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .importer import CheckedStatement, NewAccount
from .models import Account, Bank, Category, Source, Subcategory, Transaction

NEW = "new"


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file field that takes several files and cleans to a list of them."""

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        clean_one = super().clean
        if not data:
            return [clean_one(None, initial)] if self.required else []
        return [clean_one(file, initial) for file in data]


class StatementFileForm(forms.Form):
    """The Statement files: uploaded (several at once), or one carried along by the Account step as
    base64 `content`. Cleans to `files`, a list of (filename, content)."""

    file = MultipleFileField(label=_("Statement files"), required=False)
    content = forms.CharField(widget=forms.HiddenInput, required=False)
    filename = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean(self):
        super().clean()
        data = self.cleaned_data
        if uploads := data.get("file"):
            data["files"] = [(upload.name, upload.read()) for upload in uploads]
        elif data.get("content") and data.get("filename"):
            try:
                data["files"] = [
                    (data["filename"], base64.b64decode(data["content"], validate=True))
                ]
            except binascii.Error as err:
                raise forms.ValidationError(_("Upload the Statement file again.")) from err
        else:
            self.add_error("file", _("Choose a Statement file."))
        return data


class AccountForm(forms.Form):
    """Which Account a Statement goes into, when its IBAN didn't tell: one of the Statement's bank,
    or a new one."""

    account = forms.ChoiceField(label=_("Account"))
    new_account_name = forms.CharField(label=_("New Account name"), max_length=100, required=False)

    def __init__(self, *args, statement: CheckedStatement, **kwargs):
        super().__init__(*args, **kwargs)
        bank = Bank(statement.parsed.bank)
        accounts = Account.objects.filter(bank=bank)
        cast(forms.ChoiceField, self.fields["account"]).choices = [
            ("", _("Choose an Account")),
            *((str(a.pk), a.name) for a in accounts),
            (NEW, _("New %(bank)s Account") % {"bank": bank.label}),
        ]
        if not accounts:
            self.initial.update(account=NEW, new_account_name=bank.label)
        elif len(accounts) == 1 and not statement.parsed.iban:
            # A Statement with no IBAN (a Revolut CSV) most likely goes into the bank's only Account.
            self.initial["account"] = str(accounts[0].pk)

    def clean(self):
        super().clean()
        data = self.cleaned_data
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
        cast(forms.ChoiceField, self.fields["outcome"]).choices = [
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
        label=_("Account"),
        queryset=Account.objects.all(),
        required=False,
        empty_label=_("All Accounts"),
    )
    # "unresolved", "transfer", "category-<id>" or "subcategory-<id>".
    outcome = forms.ChoiceField(label=_("Outcome"), required=False)

    def __init__(self, *args, categories, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ChoiceField, self.fields["outcome"]).choices = [
            ("", _("All outcomes")),
            ("unresolved", _("Awaiting review")),
            (TRANSFER, _("Transfer")),
            *(
                (
                    category.name,
                    [
                        (
                            f"category-{category.pk}",
                            _("All of %(category)s") % {"category": category.name},
                        ),
                        *((f"subcategory-{s.pk}", s.name) for s in category.subcategories.all()),
                    ],
                )
                for category in categories
            ),
        ]

    def filter(self, transactions):
        if not self.is_valid():
            return transactions.none()
        data = self.cleaned_data
        if q := data["q"].strip():
            transactions = transactions.filter(
                Q(description__unaccent__icontains=q)
                | Q(counterparty_name__unaccent__icontains=q)
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
            transactions = transactions.filter(
                subcategory__category=outcome.removeprefix("category-")
            )
        elif outcome.startswith("subcategory-"):
            transactions = transactions.filter(subcategory=outcome.removeprefix("subcategory-"))
        return transactions


class CategoryForm(forms.Form):
    name = forms.CharField(
        label=_("Name"), max_length=100, error_messages={"required": _("Name the Category.")}
    )
    kind = forms.ChoiceField(label=_("Kind"), choices=Category.Kind.choices)


class NameForm(forms.Form):
    """Renames a Category, or names or renames a Subcategory."""

    name = forms.CharField(
        label=_("Name"), max_length=100, error_messages={"required": _("Give it a name.")}
    )
