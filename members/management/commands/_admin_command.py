import getpass
import os

from axes.utils import reset
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

PASSWORD_ENV = "PURSEGRAPH_PASSWORD"


class AdminCommand(BaseCommand):
    """Shared shape of the shell-only admin commands: one username, a new password, an active admin at the end."""

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--noinput",
            action="store_true",
            help=f"Don't prompt; read the password from the {PASSWORD_ENV} environment variable.",
        )

    def handle(self, *args, username, noinput, **options):
        Member = get_user_model()
        with transaction.atomic():
            member = self.get_member(Member, username)
            member.set_password(self.read_password(member, noinput))
            member.is_active = True
            member.is_admin = True
            member.save()
        reset(username=username)
        self.stdout.write(self.style.SUCCESS(self.success_message(username)))

    def get_member(self, Member, username):
        raise NotImplementedError

    def success_message(self, username):
        raise NotImplementedError

    def read_password(self, member, noinput):
        if noinput:
            password = os.environ.get(PASSWORD_ENV)
            if not password:
                raise CommandError(f"--noinput needs the password in {PASSWORD_ENV}.")
        else:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("The passwords didn't match.")
        try:
            validate_password(password, member)
        except ValidationError as e:
            raise CommandError(" ".join(e.messages)) from e
        return password
