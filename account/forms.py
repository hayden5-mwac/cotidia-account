"""Custom registration forms that expects an email address as a username."""
import hashlib
import os

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, get_user_model
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, PasswordChangeForm, ReadOnlyPasswordHashField

from account.models import User

def get_md5_hexdigest(email):
    """
    Returns an md5 hash for a given email.

    The length is 30 so that it fits into Django's ``User.username`` field.

    """
    return hashlib.md5(email).hexdigest()[0:30]


def generate_username(email):
    """
    Generates a unique username for the given email.

    The username will be an md5 hash of the given email. If the username exists
    we just append `a` to the email until we get a unique md5 hash.

    """
    try:
        User.objects.get(email=email)
        raise Exception('Cannot generate new username. A user with this email'
                        'already exists.')
    except User.DoesNotExist:
        pass

    username = get_md5_hexdigest(email)
    found_unique_username = False
    while not found_unique_username:
        try:
            User.objects.get(username=username)
            email = '{0}a'.format(email.lower())
            username = get_md5_hexdigest(email)
        except User.DoesNotExist:
            found_unique_username = True
            return username


class EmailAuthenticationForm(AuthenticationForm):
    required_css_class = 'required'
    remember_me = forms.BooleanField(
        required=False,
        label=_('Remember me for two weeks'),
    )
    username = forms.EmailField(
        label='', 
        max_length=256, 
        widget=forms.TextInput(attrs={'placeholder':_("Email")})
        )
    password = forms.CharField(
        label='', 
        max_length=256, 
        widget=forms.PasswordInput(attrs={'placeholder':_("Password")})
        )

    def __init__(self, *args, **kwargs):
        super(EmailAuthenticationForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            if field in ['username', 'password']:
                self.fields[field].widget.attrs['class'] = 'form__text'

    def clean_username(self):
        """Prevent case-sensitive erros in email/username."""
        return self.cleaned_data['username'].lower()


class AccountPasswordResetForm(PasswordResetForm):
    required_css_class = 'required'

    email = forms.EmailField(
        label='', 
        max_length=256, 
        widget=forms.TextInput(attrs={'placeholder':_("Email")})
        )

    def __init__(self, *args, **kwargs):
        super(AccountPasswordResetForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form__text'

    def clean_email(self):
        email = self.cleaned_data['email']

        UserModel = get_user_model()
        active_users = UserModel._default_manager.filter(
            email__iexact=email, is_active=True)
        if active_users.count() == 0:
            raise forms.ValidationError(_('There are no active accounts associated to this email.'))

        return email

    def save(self, *args, **kwargs):
        request = kwargs['request']
        domain_override = settings.SITE_URL
        super(AccountPasswordResetForm, self).save(domain_override, *args, **kwargs)

class AccountSetPasswordForm(SetPasswordForm):
    required_css_class = 'required'

    def __init__(self, *args, **kwargs):
        super(AccountSetPasswordForm, self).__init__(*args, **kwargs)

        self.fields['new_password1'].label = ''
        self.fields['new_password1'].widget.attrs['placeholder'] = _("New password")
        self.fields['new_password2'].label = ''
        self.fields['new_password2'].widget.attrs['placeholder'] = _("New password confirmation")

        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form__text'


class AccountPasswordChangeForm(PasswordChangeForm):
    
    """
    A form that change the password for the logged in user. The old password is asked to Validate
    its identity
    """

    old_password = forms.CharField(
        label="",
        widget=forms.PasswordInput(attrs={'placeholder':_("Old password"), 'class':'form__text'})
        )

    def __init__(self, *args, **kwargs):
        super(AccountPasswordChangeForm, self).__init__(*args, **kwargs)

        self.fields['new_password1'].label = ''
        self.fields['new_password1'].widget.attrs['placeholder'] = _("New password")
        self.fields['new_password2'].label = ''
        self.fields['new_password2'].widget.attrs['placeholder'] = _("New password confirmation")

        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form__text'


class UpdateDetailsForm(forms.ModelForm):

    email = forms.EmailField(label='',
        widget=forms.TextInput(attrs={'placeholder':_("Email address"), 'class':'form__text'}))

    class Meta:
        model = User
        fields = ('email',)

    def __init__(self, *args, **kwargs):
        super(UpdateDetailsForm, self).__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email']

        if User.objects.filter(email=email).count() > 0 and \
            self.instance.email != email:
            raise forms.ValidationError(_("This email is already used."))

        return email


class AccountUserCreationForm(forms.Form):
    """
    A form that creates a user, with no privileges, from the given username and
    password.
    """
    error_messages = {
        'password_mismatch': _("The two password fields didn't match."),
    }
    email = forms.EmailField(label='',
        widget=forms.TextInput(attrs={'placeholder':_("Email address"), 'class':'form__text'}))

    password1 = forms.CharField(label='',
        widget=forms.PasswordInput(attrs={'placeholder':_("Password"), 'class':'form__text'}))

    password2 = forms.CharField(label='',
        widget=forms.PasswordInput(attrs={'placeholder':_("Password Confirmation"), 'class':'form__text'}),
        help_text=_("Enter the same password as before, for verification."))

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['password_mismatch'],
                code='password_mismatch',
            )
        return password2

    def clean_email(self):
        email = self.cleaned_data['email']

        # Force all emails to be lowercase
        email = email.lower()
        
        if User.objects.filter(email=email).count() > 0:
            raise forms.ValidationError(_("This email is already used."))

        return email
        
class AccountUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label=_("Password"),
        help_text=_("Raw passwords are not stored, so there is no way to see "
                    "this user's password, but you can change the password "
                    "using <a href=\"password/\">this form</a>."))
    class Meta:
        model = User
        #fields = '__all__'
        exclude = ()

    def clean_email(self):
        """
        Validate that the supplied email address is unique for the
        site.
        
        """
        if self.cleaned_data.get('email') and User.objects.filter(email__iexact=self.cleaned_data['email']).exclude(username=self.cleaned_data['username']).exclude(username=self.initial['username']):
            raise forms.ValidationError(_("This email address is already in use. Please supply a different email address."))
        return self.cleaned_data['email']

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]
