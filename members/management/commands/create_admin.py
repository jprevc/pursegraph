from ._admin_command import AdminCommand, CommandError


class Command(AdminCommand):
    help = "Create an admin Member. This is how the first admin is made: there is no first-run web page."

    def get_member(self, Member, username):
        if Member.objects.filter(username=username).exists():
            raise CommandError(f"A Member named {username!r} already exists. Use recover_admin to regain access.")
        return Member(username=username)

    def success_message(self, username):
        return f"Created admin {username!r}."
