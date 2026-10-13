from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Member(AbstractUser):
    """One person in the Household who logs in. Admins manage Members, Accounts, Categories and settings."""

    # The only flag the app checks for admin rights; is_staff and is_superuser stay unused.
    is_admin = models.BooleanField(_("admin"), default=False)

    class Meta:
        verbose_name = _("member")
        verbose_name_plural = _("members")
