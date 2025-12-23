from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifier
    for authentication instead of username.
    """

    # Error messages
    EMAIL_REQUIRED_ERROR = "The Email must be set"
    FIRST_NAME_REQUIRED_ERROR = "The First Name must be set"
    LAST_NAME_REQUIRED_ERROR = "The Last Name must be set"
    STAFF_REQUIRED_ERROR = "Superuser must have is_staff=True."
    SUPERUSER_REQUIRED_ERROR = "Superuser must have is_superuser=True."

    def create_user(self, email, password, first_name, last_name, **extra_fields):
        """
        Create and save a user with the given email, password and required fields.
        """
        if not email:
            raise ValueError(self.EMAIL_REQUIRED_ERROR)
        if not first_name:
            raise ValueError(self.FIRST_NAME_REQUIRED_ERROR)
        if not last_name:
            raise ValueError(self.LAST_NAME_REQUIRED_ERROR)

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            first_name=first_name,
            last_name=last_name,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(self.STAFF_REQUIRED_ERROR)
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(self.SUPERUSER_REQUIRED_ERROR)

        return self.create_user(
            email,
            password=password,
            **extra_fields,
        )
