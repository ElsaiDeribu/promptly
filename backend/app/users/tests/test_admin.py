from http import HTTPStatus

import pytest
from django.urls import reverse

from app.users.models import User


class TestUserAdmin:
    def test_changelist(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_search(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url, data={"q": "test"})
        assert response.status_code == HTTPStatus.OK

    def test_add(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

        response = admin_client.post(
            url,
            data={
                "username": "test",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
            },
        )
        assert response.status_code == HTTPStatus.FOUND
        assert User.objects.filter(username="test").exists()

    def test_view_user(self, admin_client):
        user = User.objects.get(username="admin")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    @pytest.mark.django_db
    def test_admin_login(self, client, admin_user):
        url = reverse("admin:login")
        response = client.get(url)
        assert response.status_code == HTTPStatus.OK

        response = client.post(
            url,
            data={
                "username": admin_user.username,
                "password": "password",
                "next": "/admin/",
            },
            follow=True,
        )
        assert response.status_code == HTTPStatus.OK
        assert response.redirect_chain[0][0] == "/admin/"
        assert response.redirect_chain[0][1] == HTTPStatus.FOUND
