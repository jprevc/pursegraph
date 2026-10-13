import pytest

PASSWORD = "correct horse battery"


@pytest.fixture
def member(django_user_model):
    return django_user_model.objects.create_user(username="ana", password=PASSWORD)


@pytest.fixture
def logged_in_client(client, member):
    client.force_login(member)
    return client
