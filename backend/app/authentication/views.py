from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer
from .serializers import RegisterSerializer


class RegisterView(APIView):
    """
    Endpoint to handle the user registration
    """

    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data

        serializer = RegisterSerializer(data=data)

        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "success": "Account successfully created.",
                    "accessToken": str(refresh.access_token),
                    "user": {
                        "email": user.email,
                        "firstName": user.first_name,
                        "lastName": user.last_name,
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    Endpoint to handle the user login
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            email = serializer.validated_data["email"]
            password = serializer.validated_data["password"]

            user = authenticate(request, email=email, password=password)

            if user:
                refresh = RefreshToken.for_user(user)
                return Response(
                    {
                        "accessToken": str(refresh.access_token),
                        "user": {
                            "email": user.email,
                            "firstName": user.first_name,
                            "lastName": user.last_name,
                        },
                    },
                    status=status.HTTP_200_OK,
                )

            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CurrentUserView(APIView):
    """
    Endpoint to get the current user's data
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "user": {
                    "email": user.email,
                    "firstName": user.first_name,
                    "lastName": user.last_name,
                },
            },
            status=status.HTTP_200_OK,
        )
