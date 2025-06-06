from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from allauth.account import app_settings as account_settings
from allauth.account.internal.decorators import login_stage_required
from allauth.account.views import BaseReauthenticateView
from allauth.mfa import app_settings
from allauth.mfa.base.forms import AuthenticateForm, ReauthenticateForm
from allauth.mfa.models import Authenticator
from allauth.mfa.stages import AuthenticateStage
from allauth.mfa.utils import is_mfa_enabled
from allauth.mfa.webauthn.forms import AuthenticateWebAuthnForm
from allauth.mfa.webauthn.internal.flows import auth as webauthn_auth
from allauth.utils import get_form_class


@method_decorator(
    login_stage_required(stage=AuthenticateStage.key, redirect_urlname="account_login"),
    name="dispatch",
)
class AuthenticateView(TemplateView):
    form_class = AuthenticateForm
    webauthn_form_class = AuthenticateWebAuthnForm
    template_name = "mfa/authenticate." + account_settings.TEMPLATE_EXTENSION

    def dispatch(self, request, *args, **kwargs):
        self.stage = request._login_stage
        if not is_mfa_enabled(
            self.stage.login.user,
            [Authenticator.Type.TOTP, Authenticator.Type.WEBAUTHN],
        ):
            return HttpResponseRedirect(reverse("account_login"))
        self.form = self._build_forms()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.form.is_valid():
            return self.form_valid(self.form)
        else:
            return self.form_invalid(self.form)

    def _build_forms(self):
        posted_form = None
        AuthenticateFormClass = self.get_form_class()
        AuthenticateWebAuthnFormClass = self.get_webauthn_form_class()
        user = self.stage.login.user
        support_webauthn = "webauthn" in app_settings.SUPPORTED_TYPES
        if self.request.method == "POST":
            if "code" in self.request.POST:
                posted_form = self.auth_form = AuthenticateFormClass(
                    user=user, data=self.request.POST
                )
                self.webauthn_form = (
                    AuthenticateWebAuthnFormClass(user=user)
                    if support_webauthn
                    else None
                )
            else:
                self.auth_form = (
                    AuthenticateFormClass(user=user) if support_webauthn else None
                )
                posted_form = self.webauthn_form = AuthenticateWebAuthnFormClass(
                    user=user, data=self.request.POST
                )
        else:
            self.auth_form = AuthenticateFormClass(user=user)
            self.webauthn_form = (
                AuthenticateWebAuthnFormClass(user=user) if support_webauthn else None
            )
        return posted_form

    def get_form_class(self):
        return get_form_class(app_settings.FORMS, "authenticate", self.form_class)

    def get_webauthn_form_class(self):
        return get_form_class(
            app_settings.FORMS, "authenticate_webauthn", self.webauthn_form_class
        )

    def form_valid(self, form):
        form.save()
        return self.stage.exit()

    def form_invalid(self, form):
        return super().get(self.request)

    def get_context_data(self, **kwargs):
        ret = super().get_context_data()
        ret.update(
            {
                "form": self.auth_form,
                "MFA_SUPPORTED_TYPES": app_settings.SUPPORTED_TYPES,
            }
        )
        if self.webauthn_form:
            request_options = webauthn_auth.begin_authentication(self.stage.login.user)
            ret.update(
                {
                    "webauthn_form": self.webauthn_form,
                    "js_data": {"request_options": request_options},
                }
            )
        return ret


from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

import pytest

from allauth.account.models import EmailAddress


@pytest.fixture(autouse=True)
def email_verification_settings(settings):
    settings.ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
    settings.ACCOUNT_EMAIL_VERIFICATION = "mandatory"
    settings.ACCOUNT_AUTHENTICATION_METHOD = "email"
    return settings


@pytest.mark.parametrize(
    "query,expected_url",
    [
        ("", settings.LOGIN_REDIRECT_URL),
        ("?next=/foo", "/foo"),
    ],
)
def test_signup(
    client,
    db,
    settings,
    password_factory,
    get_last_email_verification_code,
    query,
    expected_url,
    mailoutbox,
):
    password = password_factory()
    resp = client.post(
        reverse("account_signup") + query,
        {
            "username": "johndoe",
            "email": "john@example.com",
            "password1": password,
            "password2": password,
        },
    )
    assert get_user_model().objects.filter(username="johndoe").count() == 1
    code = get_last_email_verification_code(client, mailoutbox)
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_email_verification_sent")
    resp = client.get(reverse("account_email_verification_sent"))
    assert resp.status_code == 200
    resp = client.post(reverse("account_email_verification_sent"), data={"code": code})
    assert resp.status_code == 302
    assert resp["location"] == expected_url


def test_signup_prevent_enumeration(
    client, db, settings, password_factory, user, mailoutbox
):
    password = password_factory()
    resp = client.post(
        reverse("account_signup"),
        {
            "username": "johndoe",
            "email": user.email,
            "password1": password,
            "password2": password,
        },
    )
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_email_verification_sent")
    assert not get_user_model().objects.filter(username="johndoe").exists()
    assert mailoutbox[0].subject == "[example.com] Account Already Exists"
    resp = client.get(reverse("account_email_verification_sent"))
    assert resp.status_code == 200
    resp = client.post(reverse("account_email_verification_sent"), data={"code": ""})
    assert resp.status_code == 200
    assert resp.context["form"].errors == {"code": ["This field is required."]}
    resp = client.post(reverse("account_email_verification_sent"), data={"code": "123"})
    assert resp.status_code == 200
    assert resp.context["form"].errors == {"code": ["Incorrect code."]}
    # Max attempts
    resp = client.post(reverse("account_email_verification_sent"), data={"code": "456"})
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_login")


@pytest.mark.parametrize("change_email", (False, True))
def test_add_or_change_email(
    auth_client,
    user,
    get_last_email_verification_code,
    change_email,
    settings,
    mailoutbox,
):
    settings.ACCOUNT_CHANGE_EMAIL = change_email
    email = "additional@email.org"
    assert EmailAddress.objects.filter(user=user).count() == 1
    with patch("allauth.account.signals.email_added") as email_added_signal:
        with patch("allauth.account.signals.email_changed") as email_changed_signal:
            resp = auth_client.post(
                reverse("account_email"), {"action_add": "", "email": email}
            )
            assert resp["location"] == reverse("account_email_verification_sent")
            assert not email_added_signal.send.called
            assert not email_changed_signal.send.called
    assert EmailAddress.objects.filter(email=email).count() == 0
    code = get_last_email_verification_code(auth_client, mailoutbox)
    resp = auth_client.get(reverse("account_email_verification_sent"))
    assert resp.status_code == 200
    with patch("allauth.account.signals.email_added") as email_added_signal:
        with patch("allauth.account.signals.email_changed") as email_changed_signal:
            with patch(
                "allauth.account.signals.email_confirmed"
            ) as email_confirmed_signal:
                resp = auth_client.post(
                    reverse("account_email_verification_sent"), data={"code": code}
                )
                assert resp.status_code == 302
                assert resp["location"] == settings.LOGIN_REDIRECT_URL
                assert email_added_signal.send.called
                assert email_confirmed_signal.send.called
                assert email_changed_signal.send.called == change_email
    assert EmailAddress.objects.filter(email=email, verified=True).count() == 1
    assert EmailAddress.objects.filter(user=user).count() == (1 if change_email else 2)


def test_email_verification_login_redirect(
    client, db, settings, password_factory, email_verification_settings
):
    password = password_factory()
    resp = client.post(
        reverse("account_signup"),
        {
            "username": "johndoe",
            "email": "user@email.org",
            "password1": password,
            "password2": password,
        },
    )
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_email_verification_sent")
    resp = client.get(reverse("account_login"))
    assert resp["location"] == reverse("account_email_verification_sent")


def test_email_verification_rate_limits(
    db,
    user_password,
    email_verification_settings,
    settings,
    user_factory,
    password_factory,
    enable_cache,
):
    settings.ACCOUNT_RATE_LIMITS = {"confirm_email": "1/m/key"}
    email = "user@email.org"
    user_factory(email=email, email_verified=False, password=user_password)
    for attempt in range(2):
        resp = Client().post(
            reverse("account_login"),
            {
                "login": email,
                "password": user_password,
            },
        )
        if attempt == 0:
            assert resp.status_code == 302
            assert resp["location"] == reverse("account_email_verification_sent")
        else:
            assert resp.status_code == 200
            assert resp.context["form"].errors == {
                "__all__": ["Too many failed login attempts. Try again later."]
            }

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

import pytest

from allauth.account.models import EmailAddress


@pytest.fixture(autouse=True)
def email_verification_settings(settings):
    settings.ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
    settings.ACCOUNT_EMAIL_VERIFICATION = "mandatory"
    settings.ACCOUNT_AUTHENTICATION_METHOD = "email"
    return settings


@pytest.mark.parametrize(
    "query,expected_url",
    [
        ("", settings.LOGIN_REDIRECT_URL),
        ("?next=/foo", "/foo"),
    ],
)
def test_signup(
    client,
    db,
    settings,
    password_factory,
    get_last_email_verification_code,
    query,
    expected_url,
    mailoutbox,
):
    password = password_factory()
    resp = client.post(
        reverse("account_signup") + query,
        {
            "username": "johndoe",
            "email": "john@example.com",
            "password1": password,
            "password2": password,
        },
    )
    assert get_user_model().objects.filter(username="johndoe").count() == 1
    code = get_last_email_verification_code(client, mailoutbox)
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_email_verification_sent")
    resp = client.get(reverse("account_email_verification_sent"))
    assert resp.status_code == 200
    resp = client.post(reverse("account_email_verification_sent"), data={"code": code})
    assert resp.status_code == 302
    assert resp["location"] == expected_url


def test_signup_prevent_enumeration(
    client, db, settings, password_factory, user, mailoutbox
):
    password = password_factory()
    resp = client.post(
        reverse("account_signup"),
        {
            "username": "johndoe",
            "email": user.email,
            "password1": password,
            "password2": password,
        },
    )
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_email_verification_sent")
    assert not get_user_model().objects.filter(username="johndoe").exists()
    assert mailoutbox[0].subject == "[example.com] Account Already Exists"
    resp = client.get(reverse("account_email_verification_sent"))
    assert resp.status_code == 200
    resp = client.post(reverse("account_email_verification_sent"), data={"code": ""})
    assert resp.status_code == 200
    assert resp.context["form"].errors == {"code": ["This field is required."]}
    resp = client.post(reverse("account_email_verification_sent"), data={"code": "123"})
    assert resp.status_code == 200
    assert resp.context["form"].errors == {"code": ["Incorrect code."]}
    # Max attempts
    resp = client.post(reverse("account_email_verification_sent"), data={"code": "456"})
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_login")


@pytest.mark.parametrize("change_email", (False, True))
def test_add_or_change_email(
    auth_client,
    user,
    get_last_email_verification_code,
    change_email,
    settings,
    mailoutbox,
):
    settings.ACCOUNT_CHANGE_EMAIL = change_email
    email = "additional@email.org"
    assert EmailAddress.objects.filter(user=user).count() == 1
    with patch("allauth.account.signals.email_added") as email_added_signal:
        with patch("allauth.account.signals.email_changed") as email_changed_signal:
            resp = auth_client.post(
                reverse("account_email"), {"action_add": "", "email": email}
            )
            assert resp["location"] == reverse("account_email_verification_sent")
            assert not email_added_signal.send.called
            assert not email_changed_signal.send.called
    assert EmailAddress.objects.filter(email=email).count() == 0
    code = get_last_email_verification_code(auth_client, mailoutbox)
    resp = auth_client.get(reverse("account_email_verification_sent"))
    assert resp.status_code == 200
    with patch("allauth.account.signals.email_added") as email_added_signal:
        with patch("allauth.account.signals.email_changed") as email_changed_signal:
            with patch(
                "allauth.account.signals.email_confirmed"
            ) as email_confirmed_signal:
                resp = auth_client.post(
                    reverse("account_email_verification_sent"), data={"code": code}
                )
                assert resp.status_code == 302
                assert resp["location"] == settings.LOGIN_REDIRECT_URL
                assert email_added_signal.send.called
                assert email_confirmed_signal.send.called
                assert email_changed_signal.send.called == change_email
    assert EmailAddress.objects.filter(email=email, verified=True).count() == 1
    assert EmailAddress.objects.filter(user=user).count() == (1 if change_email else 2)


def test_email_verification_login_redirect(
    client, db, settings, password_factory, email_verification_settings
):
    password = password_factory()
    resp = client.post(
        reverse("account_signup"),
        {
            "username": "johndoe",
            "email": "user@email.org",
            "password1": password,
            "password2": password,
        },
    )
    assert resp.status_code == 302
    assert resp["location"] == reverse("account_email_verification_sent")
    resp = client.get(reverse("account_login"))
    assert resp["location"] == reverse("account_email_verification_sent")


def test_email_verification_rate_limits(
    db,
    user_password,
    email_verification_settings,
    settings,
    user_factory,
    password_factory,
    enable_cache,
):
    settings.ACCOUNT_RATE_LIMITS = {"confirm_email": "1/m/key"}
    email = "user@email.org"
    user_factory(email=email, email_verified=False, password=user_password)
    for attempt in range(2):
        resp = Client().post(
            reverse("account_login"),
            {
                "login": email,
                "password": user_password,
            },
        )
        if attempt == 0:
            assert resp.status_code == 302
            assert resp["location"] == reverse("account_email_verification_sent")
        else:
            assert resp.status_code == 200
            assert resp.context["form"].errors == {
                "__all__": ["Too many failed login attempts. Try again later."]
            }


