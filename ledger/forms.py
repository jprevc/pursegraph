from django import forms
from django.utils.translation import gettext_lazy as _

from .importer import NewAccount
from .models import Account, Bank

NEW = "new"


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file field that takes several files and cleans to a list of them."""

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return [super().clean(None, initial)]
        return [super(MultipleFileField, self).clean(file, initial) for file in data]


class ImportForm(forms.Form):
    """A Revolut CSV has no IBAN, so the Member picks the Account (or creates one) up front.

    Several Statement files can be uploaded at once; they all go into the chosen Account.
    """

    file = MultipleFileField(label=_("Statement files"))
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
