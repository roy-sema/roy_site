from django import forms
from django.utils.translation import gettext_lazy as _

from allauth.core import context
from allauth.mfa import app_settings
from allauth.mfa.adapter import get_adapter
from allauth.mfa.base.internal.flows import (
    check_rate_limit,
    post_authentication,
)
from allauth.mfa.models import Authenticator
from allauth.mfa.webauthn.internal import auth, flows


class _BaseAddWebAuthnForm(forms.Form):
    name = forms.CharField(required=False)
    credential = forms.JSONField(required=True, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        initial = kwargs.setdefault("initial", {})
        initial.setdefault(
            "name",
            get_adapter().generate_authenticator_name(
                self.user, Authenticator.Type.WEBAUTHN
            ),
        )
        super().__init__(*args, **kwargs)

    def clean_name(self):
        """
        We don't want to make `name` a required field, as the WebAuthn
        ceremony happens before posting the resulting credential, and we don't
        want to reject a valid credential because of a missing name -- it might
        be resident already. So, gracefully plug in a name.
        """
        name = self.cleaned_data["name"]
        if not name:
            name = get_adapter().generate_authenticator_name(
                self.user, Authenticator.Type.WEBAUTHN
            )
        return name

    def clean(self):
        cleaned_data = super().clean()
        credential = cleaned_data.get("credential")
        if credential:
            # Explicitly parse JSON payload -- otherwise, register_complete()
            # crashes with some random TypeError and we don't want to do
            # Pokemon-style exception handling.
            auth.parse_registration_response(credential)
            auth.complete_registration(credential)
        return cleaned_data


class AddWebAuthnForm(_BaseAddWebAuthnForm):
    if app_settings.PASSKEY_LOGIN_ENABLED:
        passwordless = forms.BooleanField(
            label=_("Passwordless"),
            required=False,
            help_text=_(
                "Enabling passwordless operation allows you to sign in using just this key, but imposes additional requirements such as biometrics or PIN protection."
            ),
        )



from django.test import RequestFactory, TestCase
from django.utils.http import base36_to_int, int_to_base36
from django.views import csrf

from allauth import app_settings, utils


class BasicTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_generate_unique_username(self):
        examples = [
            ("a.b-c@example.com", "a.b-c"),
            ("Üsêrnamê", "username"),
            ("User Name", "user_name"),
            ("", "user"),
        ]
        for input, username in examples:
            self.assertEqual(utils.generate_unique_username([input]), username)

    def test_email_validation(self):
        s = "this.email.address.is.a.bit.too.long.but.should.still.validate@example.com"  # noqa
        self.assertEqual(s, utils.valid_email_or_none(s))

    def test_build_absolute_uri(self):
        request = None
        if not app_settings.SITES_ENABLED:
            request = self.factory.get("/")
            request.META["SERVER_NAME"] = "example.com"
        self.assertEqual(
            utils.build_absolute_uri(request, "/foo"), "http://example.com/foo"
        )
        self.assertEqual(
            utils.build_absolute_uri(request, "/foo", protocol="ftp"),
            "ftp://example.com/foo",
        )
        self.assertEqual(
            utils.build_absolute_uri(request, "http://foo.com/bar"),
            "http://foo.com/bar",
        )

    def test_int_to_base36(self):
        n = 55798679658823689999
        b36 = "brxk553wvxbf3"
        assert int_to_base36(n) == b36
        assert base36_to_int(b36) == n

    def test_templatetag_with_csrf_failure(self):
        # Generate a fictitious GET request
        from allauth.socialaccount.models import SocialApp

        app = SocialApp.objects.create(provider="google")
        if app_settings.SITES_ENABLED:
            from django.contrib.sites.models import Site

            app.sites.add(Site.objects.get_current())

        request = self.factory.get("/tests/test_403_csrf.html")
        # Simulate a CSRF failure by calling the View directly
        # This template is using the `provider_login_url` templatetag
        response = csrf.csrf_failure(request, template_name="tests/test_403_csrf.html")
        # Ensure that CSRF failures with this template
        # tag succeed with the expected 403 response
        self.assertEqual(response.status_code, 403)

