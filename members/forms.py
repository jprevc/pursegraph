from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _


def name_field():
    """A Member's name, as the Dashboard shows it. The whole name goes into first_name: the app never splits names."""
    return forms.CharField(label=_("Name"), max_length=150)


class NewMemberForm(forms.ModelForm):
    name = name_field()

    class Meta:
        model = get_user_model()
        fields = ["username"]

    def save(self, commit=True):
        member = super().save(commit=False)
        member.first_name = self.cleaned_data["name"]
        # Unusable until the Member sets one through their invite link.
        member.set_unusable_password()
        if commit:
            member.save()
        return member


class RenameMemberForm(forms.Form):
    name = name_field()
