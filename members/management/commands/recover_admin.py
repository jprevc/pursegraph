from ._admin_command import AdminCommand, CommandError


class Command(AdminCommand):
    help = (
        "Regain access as a locked-out admin: set a new password, reactivate the Member, "
        "make them an admin and clear their failed-login lockout."
    )

    def get_member(self, Member, username):
        try:
            return Member.objects.select_for_update().get(username=username)
        except Member.DoesNotExist:
            raise CommandError(f"No Member named {username!r}. Use create_admin to make one.") from None

    def success_message(self, username):
        return f"Recovered admin {username!r}."
