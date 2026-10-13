import pytest

USERNAME = "ana"
PASSWORD = "correct horse battery"


def log_in(client, username=USERNAME, password=PASSWORD):
    return client.post("/login/", {"username": username, "password": password})


@pytest.fixture
def member(django_user_model):
    return django_user_model.objects.create_user(username=USERNAME, password=PASSWORD)


@pytest.fixture
def logged_in_client(client, member):
    client.force_login(member)
    return client
