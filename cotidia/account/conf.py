from django.conf import settings

from appconf import AppConf


class AccountConf(AppConf):
    ADMIN_LOGIN_URL = '/admin/login/'
    PUBLIC_LOGIN_URL = '/account/login/'

    # Force the user to activate their account via email before being allowed
    # to login
    FORCE_ACTIVATION = True

    ALLOW_SIGN_IN = True
    ALLOW_SIGN_UP = True

    # Change the standard one-factor authentication workflow to a two-factor
    # workflow.
    ENABLE_TWO_FACTOR = False
    # Force all admin users to sign in using two-factor authentication.
    # Only applies if `ENABLE_TWO_FACTOR` is set to `True`.
    FORCE_ADMIN_TWO_FACTOR = False

    class Meta:
        prefix = 'account'