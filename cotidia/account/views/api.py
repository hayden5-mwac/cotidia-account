from django.db import transaction
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator as token_generator
from django.urls import reverse

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from cotidia.account import signals
from cotidia.account.conf import settings
from cotidia.account.serializers import (
    SignUpSerializer,
    SignInTokenSerializer,
    AuthenticateTokenSerializer,
    UserSerializer,
    ResetPasswordSerializer,
    SetPasswordSerializer,
    ChangePasswordSerializer,
)
from cotidia.account.models import User
from cotidia.account.notices import ResetPasswordNotice


class SignUp(APIView):
    """Handle the creation of a new account."""

    authentication_classes = ()
    permission_classes = ()
    serializer_class = SignUpSerializer
    user_serializer_class = UserSerializer

    def get_serializer_class(self):
        return self.serializer_class

    def get_user_serializer_class(self):
        return self.user_serializer_class

    @transaction.atomic
    def post(self, request):
        if settings.ACCOUNT_ALLOW_SIGN_UP is False:
            return Response(
                {"message": "SIGN_UP_DISABLED"}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer_class = self.get_serializer_class()
        user_serializer_class = self.get_user_serializer_class()

        serializer = serializer_class(data=request.data)

        if serializer.is_valid():

            user = serializer.save()

            if settings.ACCOUNT_FORCE_ACTIVATION is True:
                user.send_activation_link(app=True)

            token, created = Token.objects.get_or_create(user=user)

            data = {"token": token.key}
            data.update(user_serializer_class(token.user).data)

            signals.user_sign_up.send(sender=None, request=request, user=user)

            return Response(data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SignIn(APIView):
    """Sign in a user with email and password."""

    authentication_classes = ()
    permission_classes = ()
    serializer_class = SignInTokenSerializer
    user_serializer_class = UserSerializer
    model = Token

    def get_serializer_class(self):
        return self.serializer_class

    def get_user_serializer_class(self):
        return self.user_serializer_class

    @transaction.atomic
    def post(self, request):

        if settings.ACCOUNT_ALLOW_SIGN_IN is False:
            return Response(
                {"message": "Sign in disabled."}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer_class = self.get_serializer_class()
        user_serializer_class = self.get_user_serializer_class()

        serializer = serializer_class(data=request.data)

        if serializer.is_valid():

            user = authenticate(
                username=serializer.data["email"], password=serializer.data["password"]
            )
            auth_login(request, user)

            token, created = Token.objects.get_or_create(user=user)

            data = {"token": token.key}
            user = user_serializer_class(token.user)
            data.update(user.data)

            return Response(data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class Activate(APIView):
    """Activate a profile."""

    authentication_classes = ()
    permission_classes = ()

    @transaction.atomic
    def get(self, request, uuid, token):

        try:
            user = User.objects.get(uuid=uuid)
        except User.DoesNotExist:
            return Response(
                {"message": "USER_INVALID"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"message": "TOKEN_INVALID"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Activate now
        user.is_active = True
        user.save()

        # Send the activation signals
        signals.user_activate.send(sender=None, request=request, user=user)

        return Response({"message": "ACTIVATED"}, status=status.HTTP_200_OK)


class ResendActivationLink(APIView):
    """Resend the link to activate a user."""

    http_method_names = ["post"]
    authentication_classes = ()
    permission_classes = ()

    @transaction.atomic
    def post(self, request, uuid):

        try:
            user = User.objects.get(uuid=uuid)
        except User.DoesNotExist:
            return Response(
                {"message": "USER_INVALID"}, status=status.HTTP_400_BAD_REQUEST
            )

        if user.is_active:
            return Response(
                {"message": "USER_ACTIVE"}, status=status.HTTP_400_BAD_REQUEST
            )

        user.send_activation_link(app=True)

        return Response({"message": "ACTIVATION_SENT"}, status=status.HTTP_200_OK)


class Authenticate(APIView):
    """Authenticate with a given token."""

    authentication_classes = ()
    permission_classes = ()
    serializer_class = AuthenticateTokenSerializer

    @transaction.atomic
    def post(self, request, user_serializer_class=None):

        if user_serializer_class is None:
            user_serializer_class = UserSerializer

        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            try:
                token = Token.objects.get(key=serializer.data["token"])
            except Token.DoesNotExist:
                return Response(
                    {"message": "TOKEN_INVALID"}, status=status.HTTP_400_BAD_REQUEST
                )

            if not token.user.is_active:
                return Response(
                    {"message": "USER_INACTIVE"}, status=status.HTTP_400_BAD_REQUEST
                )

            user = user_serializer_class(token.user)

            return Response(user.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResetPassword(APIView):
    """Reset the password for an exiting user."""

    authentication_classes = ()
    permission_classes = ()

    @transaction.atomic
    def post(self, request):

        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = User.objects.get(email=serializer.data["email"])
        except User.DoesNotExist:
            user = None

        if user:

            if not user.is_active:
                return Response(
                    {"non_field_errors": ["Your account is not active."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            token = default_token_generator.make_token(user)

            if hasattr(settings, "APP_URL"):
                url = "{0}/reset-password/{1}/{2}/".format(
                    settings.APP_URL, user.uuid, token
                )
            else:
                url = settings.SITE_URL + reverse(
                    "account-public:password_reset_confirm",
                    kwargs={
                        "uidb64": urlsafe_base64_encode(force_bytes(user.pk)).decode(),
                        "token": token_generator.make_token(user),
                    },
                )

            notice = ResetPasswordNotice(
                recipients=["%s <%s>" % (user.get_full_name(), user.email)],
                context={"url": url, "first_name": user.first_name},
            )
            notice.send(force_now=True)

        return Response({"message": "PASSWORD_RESET"}, status=status.HTTP_200_OK)


class ResetPasswordValidate(APIView):
    """Validate the reset password key."""

    authentication_classes = ()
    permission_classes = ()

    @transaction.atomic
    def get(self, request, uuid, token):

        try:
            user = User.objects.get(uuid=uuid)
        except User.DoesNotExist:
            return Response(
                {"message": "USER_INVALID"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"message": "TOKEN_INVALID"}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"message": "TOKEN_VALID"}, status=status.HTTP_200_OK)


class SetPassword(APIView):
    """Set the new password."""

    authentication_classes = ()
    permission_classes = ()

    @transaction.atomic
    def post(self, request, uuid, token):

        try:
            user = User.objects.get(uuid=uuid)
        except User.DoesNotExist:
            return Response(
                {"message": "USER_INVALID"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"message": "TOKEN_INVALID"}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Set the new password
        user.set_password(serializer.data["password1"])
        user.save()

        return Response({"message": "PASSWORD_SET"}, status=status.HTTP_200_OK)


class UpdateDetails(APIView):
    """Update the user details."""

    def get_serializer_class(self):
        return UserSerializer

    @transaction.atomic
    def post(self, request, serializer_class=None):

        if serializer_class is None:
            serializer_class = self.get_serializer_class()

        serializer = serializer_class(instance=request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)


class ChangePassword(APIView):
    """Change the current password."""

    @transaction.atomic
    def post(self, request):

        serializer = ChangePasswordSerializer(data=request.data, user=request.user)
        serializer.is_valid(raise_exception=True)

        # Set the new password
        request.user.set_password(serializer.data["password1"])
        request.user.save()

        return Response({"message": "PASSWORD_CHANGED"}, status=status.HTTP_200_OK)
