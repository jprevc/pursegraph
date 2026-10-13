import base64
import binascii

from django import forms
from django.utils.translation import gettext_lazy as _

from .importer import CheckedStatement, NewAccount
from .models import Account, Bank

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
        data = super().clean()
        if uploads := data.get("file"):
            data["files"] = [(upload.name, upload.read()) for upload in uploads]
        elif data.get("content") and data.get("filename"):
            try:
                data["files"] = [(data["filename"], base64.b64decode(data["content"], validate=True))]
            except binascii.Error:
                raise forms.ValidationError(_("Upload the Statement file again."))
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
        self.fields["account"].choices = [
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
        data = super().clean()
        if data.get("account") == NEW and not data.get("new_account_name", "").strip():
            self.add_error("new_account_name", _("Name the new Account."))
        return data

    def chosen_account(self) -> Account | NewAccount:
        if self.cleaned_data["account"] == NEW:
            return NewAccount(self.cleaned_data["new_account_name"].strip())
        return Account.objects.get(pk=self.cleaned_data["account"])
