from rest_framework import serializers

from app.users.models import User

# Error messages
PASSWORDS_DO_NOT_MATCH_ERROR = "Password did not match."
EMAIL_ALREADY_USED_ERROR = "Email is already used."


class LoginSerializer(serializers.Serializer):
    """
    Schema for Login
    """

    email = serializers.EmailField()
    password = serializers.CharField()


class RegisterSerializer(serializers.Serializer):
    """
    Schema for Account Registration
    """

    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    password = serializers.CharField()
    confirm_password = serializers.CharField()

    def validate(self, data):
        """
        Handles the validation for the email and password
        """
        if data.get("password") != data.get("confirm_password"):
            raise serializers.ValidationError(PASSWORDS_DO_NOT_MATCH_ERROR)

        if User.objects.filter(email=data.get("email")).exists():
            raise serializers.ValidationError(EMAIL_ALREADY_USED_ERROR)

        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        return User.objects.create_user(
            email=self.validated_data["email"],
            first_name=self.validated_data["first_name"],
            last_name=self.validated_data["last_name"],
            password=self.validated_data["password"],
        )
