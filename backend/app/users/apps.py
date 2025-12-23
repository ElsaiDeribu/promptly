import contextlib

from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "app.users"
    verbose_name = "Users"

    def ready(self):
        with contextlib.suppress(ImportError):
            import app.users.signals  # noqa: F401
