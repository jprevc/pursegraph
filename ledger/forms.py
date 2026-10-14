import base64
import binascii
from typing import cast

from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .importer import CheckedStatement, NewAccount
from .models import (
    Account,
    AccountIBAN,
    Bank,
    Category,
    Rule,
    Source,
    Subcategory,
    Transaction,
)
from .parsers.iban import valid_iban
from .rules import place_at_top
from .transfers import pair_by_hand

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


class AccountAdminForm(forms.ModelForm):
    """An Account as admins edit it: its name, bank, owners and IBANs, one per line.

    An Account keeps its bank while it has Statements, and one with no Statements needs an IBAN, since only
    an IBAN makes money moved to it a Transfer."""

    ibans = forms.CharField(
        label=_("IBANs"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("One per line; several when the bank re-issued the Account."),
    )

    class Meta:
        model = Account
        fields = ["name", "bank", "owners"]
        widgets = {"owners": forms.CheckboxSelectMultiple}
        error_messages = {"owners": {"required": _("Choose at least one owner.")}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cast(
            forms.ModelChoiceField, self.fields["owners"]
        ).queryset = get_user_model().objects.order_by("username")
        if self.instance.pk:
            self.initial["ibans"] = "\n".join(self.instance.ibans.values_list("iban", flat=True))

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean_bank(self):
        bank = self.cleaned_data["bank"]
        if self.instance.pk and bank != self.instance.bank and self.instance.statements.exists():
            raise forms.ValidationError(_("An Account with Statements keeps its bank."))
        return bank

    def clean_ibans(self) -> list[str]:
        ibans = list(
            dict.fromkeys(
                "".join(line.split()).upper() for line in self.cleaned_data["ibans"].splitlines()
            )
        )
        ibans = [iban for iban in ibans if iban]
        errors = [
            _("%(iban)s is not a valid IBAN.") % {"iban": iban}
            for iban in ibans
            if not valid_iban(iban)
        ]
        taken = AccountIBAN.objects.filter(iban__in=ibans).select_related("account")
        if self.instance.pk:
            taken = taken.exclude(account=self.instance)
        errors += [
            _("%(iban)s is already an IBAN of %(account)s.")
            % {"iban": t.iban, "account": t.account}
            for t in taken
        ]
        if errors:
            raise forms.ValidationError(errors)
        return ibans

    def clean(self):
        super().clean()
        data = self.cleaned_data
        if data.get("bank") == Bank.OTHER and data.get("ibans") == []:
            self.add_error(
                "ibans",
                _("An Account with no Statements needs an IBAN to recognise Transfers to it."),
            )
        return data

    def save(self, commit=True) -> Account:
        with db_transaction.atomic():
            account = super().save()
            ibans = self.cleaned_data["ibans"]
            account.ibans.exclude(iban__in=ibans).delete()
            kept = set(account.ibans.values_list("iban", flat=True))
            AccountIBAN.objects.bulk_create(
                AccountIBAN(account=account, iban=iban) for iban in ibans if iban not in kept
            )
        return account


TRANSFER = "transfer"


PAIR_WITH = "pair-"


class OutcomeForm(forms.Form):
    """A manual outcome for `transaction`: a Subcategory's id or TRANSFER; for an ambiguous pairing, also
    PAIR_WITH and the id of one of its candidates."""

    outcome = forms.ChoiceField(label=_("Outcome"))

    def __init__(self, *args, transaction: Transaction, **kwargs):
        super().__init__(*args, **kwargs)
        self.transaction = transaction
        self.candidates = {f"{PAIR_WITH}{c.pk}": c for c in transaction.pairing_candidates()}
        cast(forms.ChoiceField, self.fields["outcome"]).choices = [
            *((str(s.pk), s.name) for s in Subcategory.objects.all()),
            (TRANSFER, _("Transfer")),
            *((value, str(c)) for value, c in self.candidates.items()),
        ]

    def save(self) -> None:
        value = self.cleaned_data["outcome"]
        if value in self.candidates:
            pair_by_hand(self.transaction, self.candidates[value])
        else:
            subcategory = None if value == TRANSFER else Subcategory.objects.get(pk=value)
            self.transaction.set_outcome(subcategory, source=Source.MANUAL)


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


class RuleForm(forms.ModelForm):
    """A Rule's conditions and outcome: a Subcategory's id, or TRANSFER. A new Rule goes to the top."""

    outcome = forms.ChoiceField(label=_("Outcome"))

    class Meta:
        model = Rule
        fields = ["description_contains", "counterparty_iban", "direction", "account"]
        labels = {"direction": _("Direction")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cast(forms.ChoiceField, self.fields["direction"]).choices = [
            ("", _("In or out")),
            *Rule.Direction.choices,
        ]
        cast(forms.ModelChoiceField, self.fields["account"]).empty_label = _("Any Account")
        cast(forms.ChoiceField, self.fields["outcome"]).choices = [
            ("", _("Choose an outcome")),
            *(
                (category.name, [(str(s.pk), s.name) for s in category.subcategories.all()])
                for category in Category.objects.prefetch_related("subcategories")
            ),
            (TRANSFER, _("Transfer")),
        ]
        if self.instance.pk:
            self.initial.setdefault("outcome", self.instance.subcategory_id or TRANSFER)

    @classmethod
    def from_transaction(cls, transaction: Transaction) -> "RuleForm":
        """A new Rule for Transactions like `transaction`: its counterparty IBAN if it has one, otherwise its
        description, with its outcome."""
        initial: dict = (
            {"counterparty_iban": transaction.counterparty_iban}
            if transaction.counterparty_iban
            else {
                "description_contains": transaction.description.strip()[: Rule.DESCRIPTION_LENGTH]
            }
        )
        if transaction.subcategory_id or transaction.is_transfer:
            initial["outcome"] = transaction.subcategory_id or TRANSFER
        return cls(initial=initial)

    def clean_description_contains(self):
        return self.cleaned_data["description_contains"].strip()

    def clean_counterparty_iban(self):
        return "".join(self.cleaned_data["counterparty_iban"].split()).upper()

    def clean(self):
        super().clean()
        data = self.cleaned_data
        if not any(
            data.get(field)
            for field in ("description_contains", "counterparty_iban", "direction", "account")
        ):
            raise forms.ValidationError(_("Give the Rule at least one condition."))
        return data

    def save(self, commit=True) -> Rule:
        rule = super().save(commit=False)
        value = self.cleaned_data["outcome"]
        rule.subcategory = None if value == TRANSFER else Subcategory.objects.get(pk=value)
        if rule.pk:
            rule.save()
        else:
            place_at_top(rule)
        return rule
