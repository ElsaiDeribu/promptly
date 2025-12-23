from django.contrib.auth.models import AbstractUser
from django.db.models import CharField
from django.db.models import EmailField
from django.urls import reverse

from .manager import UserManager


class User(AbstractUser):
    """
    Default custom user model for backend_boilerplate_project.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    first_name = CharField("First Name", max_length=255, blank=True)
    last_name = CharField("Last Name", max_length=255, blank=True)
    username = None  # type: ignore[assignment]
    email = EmailField("Email address", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("api:user-detail", kwargs={"username": self.email})
