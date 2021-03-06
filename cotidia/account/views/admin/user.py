import django_filters
import importlib
import uuid

from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.apps import apps
from django import forms

from betterforms.multiform import MultiModelForm

from cotidia.account.conf import settings
from cotidia.admin.views import (
    AdminListView,
    AdminDetailView,
    AdminCreateView,
    AdminUpdateView,
    AdminDeleteView,
)
from cotidia.account.models import User
from cotidia.account.forms.admin.user import (
    UserAddForm,
    SuperUserAddForm,
    UserUpdateForm,
    SuperUserUpdateForm,
    UserChangePasswordForm,
    UserInviteForm,
)


class CheckUserMixin:
    def check_user(self, user):
        obj = self.get_object()
        if obj.is_superuser:
            if user.is_superuser:
                return True
        elif obj.is_staff:
            if user.is_superuser:
                return True
        elif user.is_staff and user.has_perm("account.change_user"):
            return True

        return False


class UserFilter(django_filters.FilterSet):
    first_name = django_filters.CharFilter(
        label="Search",
        method="search",
        widget=forms.TextInput(attrs={"placeholder": "Search"}),
    )

    class Meta:
        model = User
        fields = ["first_name"]

    def search(self, queryset, name, value):

        q_objects = (
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
        )

        try:
            val = uuid.UUID(value, version=4)
            q_objects |= Q(uuid=val)
        except ValueError:
            pass

        return queryset.filter(q_objects)


class UserList(AdminListView):
    columns = (
        ("Name", "name"),
        ("Email", "email"),
        ("Active", "is_active"),
        ("Date Joined", "date_joined"),
    )
    model = User
    row_click_action = "detail"
    row_actions = ["view"]
    filterset = UserFilter

    def get_queryset(self):
        return super().get_queryset().exclude(Q(is_staff=True) | Q(is_superuser=True))


class UserListStaff(AdminListView):
    columns = (
        ("Name", "name"),
        ("Email", "email"),
        ("Superuser", "is_superuser"),
        ("Staff", "is_staff"),
        ("Active", "is_active"),
        ("Date Joined", "date_joined"),
    )
    model = User
    row_click_action = "detail"
    row_actions = ["view"]
    filterset = UserFilter

    def check_user(self, user):
        if user.is_superuser:
            return True
        else:
            return False

    def get_queryset(self):
        return super().get_queryset().filter(is_staff=True).exclude(is_superuser=True)


class UserListSuperuser(AdminListView):
    columns = (
        ("Name", "name"),
        ("Email", "email"),
        ("Superuser", "is_superuser"),
        ("Staff", "is_staff"),
        ("Active", "is_active"),
        ("Date Joined", "date_joined"),
    )
    model = User
    row_click_action = "detail"
    row_actions = ["view"]
    filterset = UserFilter

    def check_user(self, user):
        if user.is_superuser:
            return True
        else:
            return False

    def get_queryset(self):
        return super().get_queryset().filter(is_superuser=True)


class UserDetail(CheckUserMixin, AdminDetailView):
    model = User
    fieldsets = [
        {
            "legend": "User details",
            "fields": [
                [
                    {"label": "Name", "field": "name"},
                    {"label": "Email", "field": "email"},
                ],
                [
                    {"label": "Username", "field": "username"},
                    {"label": "User ID", "field": "uuid"},
                ],
            ],
        },
        {
            "legend": "Roles & Permissions",
            "fields": [
                [
                    {"label": "Active", "field": "is_active"},
                    {"label": "Staff", "field": "is_staff"},
                    {"label": "Superuser", "field": "is_superuser"},
                ],
                {"label": "Roles", "field": "groups"},
                {"label": "Permissions", "field": "user_permissions"},
            ],
        },
    ]

    def get_fieldsets(self):
        fieldsets = self.fieldsets.copy()

        user = self.get_object()

        if settings.ACCOUNT_PROFILE_MODEL:
            app_label, model_name = settings.ACCOUNT_PROFILE_MODEL.split(".")
            profile_class = apps.get_model(app_label=app_label, model_name=model_name)

            try:
                user.profile
                has_profile = True
            except ObjectDoesNotExist:
                has_profile = False

            # profile_app_label
            if has_profile:
                label = "Edit profile"
                url = reverse(
                    "{}-admin:profile-update".format(profile_class._meta.app_label),
                    kwargs={"pk": user.profile.id},
                )
                action_class = "btn--change"
            else:
                label = "Add profile"
                url = reverse(
                    "{}-admin:profile-add".format(profile_class._meta.app_label),
                    kwargs={"user_id": user.id},
                )
                action_class = "btn--create"
            fieldsets.append(
                {
                    "legend": "People",
                    "template_name": "admin/account/user/profile.html",
                    "actions": [{"label": label, "url": url, "class": action_class}],
                }
            )
        if (
            settings.ACCOUNT_ENABLE_TWO_FACTOR
            and self.request.user.is_superuser
            and self.request.user.is_verified()
        ):
            # Show OTP options
            fieldsets.append(
                {"legend": "Security", "template_name": "admin/account/user/otp.html"}
            )
        return fieldsets


class UserCreate(AdminCreateView):
    model = User
    # form_class = UserAddForm

    def form_valid(self, form):
        response = super().form_valid(form)

        if self.object.is_active and settings.ACCOUNT_AUTO_SEND_INVITATION_EMAIL:
            self.object.send_invitation_email()

        return response

    @property
    def form_class(self):
        try:
            # This is here to throw an attribute error if it does not exist
            if settings.ACCOUNT_PROFILE_MODEL:
                module_name = ".".join(settings.ACCOUNT_PROFILE_FORM.split(".")[:-1])
                form_name = settings.ACCOUNT_PROFILE_FORM.split(".")[-1]
                module = importlib.import_module(module_name)

                class TempMultiForm(MultiModelForm):
                    form_classes = {
                        "user": self.get_single_form_class(),
                        "profile": getattr(module, form_name),
                    }

                    def save(self, commit=True):
                        objects = super(TempMultiForm, self).save(commit=False)

                        if commit:
                            user = objects["user"]
                            user.save()
                            profile = objects["profile"]
                            profile.user = user
                            profile.save()

                        return objects.get("user")

                return TempMultiForm
            else:
                return self.get_single_form_class()
        except AttributeError as e:
            # Checks to see the attribute error is raised due to the setting
            # not existing not due to the module not having the given form
            if "'ACCOUNT_PROFILE_MODEL'" in str(e):
                return self.get_single_form_class()
            else:
                # If the error is not due to a missing setting we fail loudly
                raise

    def get_single_form_class(self):
        if self.request.user.is_superuser:
            return SuperUserAddForm
        else:
            return UserAddForm


class UserUpdate(CheckUserMixin, AdminUpdateView):
    model = User

    def form_valid(self, form):
        previous_instance = self.get_object()
        response = super().form_valid(form)

        # If `is_active` change state from False to True, send the invitation
        if (
            not previous_instance.is_active
            and self.object.is_active
            and self.object.is_staff
        ):
            # Only send if the user was never invited
            if not self.object.password and settings.ACCOUNT_AUTO_SEND_INVITATION_EMAIL:
                self.object.send_invitation_email()

        return response

    def get_form_class(self):
        if self.request.user.is_superuser:
            return SuperUserUpdateForm
        else:
            return UserUpdateForm


class UserInvite(CheckUserMixin, AdminUpdateView):
    model = User
    form_class = UserInviteForm

    def get_template_names(self):
        return ["admin/account/user/invite.html"]

    def form_valid(self, form):
        response = super().form_valid(form)

        if self.object.is_active and not self.object.password:
            self.object.send_invitation_email()

        return response

    def get_success_url(self):
        messages.success(
            self.request,
            '{} has been invited. <a href="{}">View</a>'.format(
                self.model._meta.verbose_name, self.build_detail_url()
            ),
        )
        return self.build_success_url()


class UserDelete(AdminDeleteView):
    model = User

    def check_user(self, user):
        obj = self.get_object()
        if obj.is_superuser:
            if user.is_superuser:
                return True
        elif obj.is_staff:
            if user.is_superuser:
                return True
        elif user.is_staff and user.has_perm("account.delete_user"):
            return True

        return False


class UserChangePassword(CheckUserMixin, AdminUpdateView):
    model = User
    form_class = UserChangePasswordForm

    def dispatch(self, request, *args, **kwargs):
        if self.get_object() == request.user:
            return HttpResponseRedirect(reverse("account-admin:password-change"))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        del kwargs["instance"]
        kwargs["user"] = self.get_object()
        return kwargs
