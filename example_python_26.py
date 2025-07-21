from typing import Callable, Optional

from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.account.internal.flows.login import record_authentication
from allauth.core import context, ratelimit
from allauth.mfa import signals
from allauth.mfa.models import Authenticator


def delete_dangling_recovery_codes(user) -> Optional[Authenticator]:
    deleted_authenticator = None
    qs = Authenticator.objects.filter(user=user)
    if not qs.exclude(type=Authenticator.Type.RECOVERY_CODES).exists():
        deleted_authenticator = qs.first()
        qs.delete()
    return deleted_authenticator


def delete_and_cleanup(request, authenticator) -> None:
    authenticator.delete()
    rc_auth = delete_dangling_recovery_codes(authenticator.user)
    for auth in [authenticator, rc_auth]:
        if auth:
            signals.authenticator_removed.send(
                sender=Authenticator,
                request=request,
                user=request.user,
                authenticator=auth,
            )


def post_authentication(
    request,
    authenticator: Authenticator,
    reauthenticated: bool = False,
    passwordless: bool = False,
) -> None:
    authenticator.record_usage()
    extra_data = {
        "id": authenticator.pk,
        "type": authenticator.type,
    }
    if reauthenticated:
        extra_data["reauthenticated"] = True
    if passwordless:
        extra_data["passwordless"] = True
    record_authentication(request, "mfa", **extra_data)


def check_rate_limit(user) -> Callable[[], None]:
    key = f"mfa-auth-user-{str(user.pk)}"
    if not ratelimit.consume(
        context.request,
        action="login_failed",
        key=key,
    ):
        raise get_account_adapter().validation_error("too_many_login_attempts")
    return lambda: ratelimit.clear(context.request, action="login_failed", key=key)


from unittest.mock import ANY

from django.urls import reverse

import pytest
from pytest_django.asserts import assertTemplateUsed

from allauth.account.authentication import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.mfa.models import Authenticator


def test_reauthentication(auth_client, user_with_recovery_codes):
    resp = auth_client.get(reverse("mfa_view_recovery_codes"))
    assert resp.status_code == 302
    assert resp["location"].startswith(reverse("account_reauthenticate"))
    resp = auth_client.get(reverse("mfa_reauthenticate"))
    assertTemplateUsed(resp, "mfa/reauthenticate.html")
    authenticator = Authenticator.objects.get(
        user=user_with_recovery_codes, type=Authenticator.Type.RECOVERY_CODES
    )
    unused_code = authenticator.wrap().get_unused_codes()[0]
    resp = auth_client.post(reverse("mfa_reauthenticate"), data={"code": unused_code})
    assert resp.status_code == 302
    resp = auth_client.get(reverse("mfa_view_recovery_codes"))
    assert resp.status_code == 200
    assertTemplateUsed(resp, "mfa/recovery_codes/index.html")
    methods = auth_client.session[AUTHENTICATION_METHODS_SESSION_KEY]
    assert methods[-1] == {
        "method": "mfa",
        "type": "recovery_codes",
        "id": authenticator.pk,
        "at": ANY,
        "reauthenticated": True,
    }


@pytest.mark.parametrize(
    "url_name",
    (
        "mfa_activate_totp",
        "mfa_index",
        "mfa_deactivate_totp",
    ),
)
def test_login_required_views(client, url_name):
    resp = client.get(reverse(url_name))
    assert resp.status_code == 302
    assert resp["location"].startswith(reverse("account_login"))


def test_index(auth_client, user_with_totp):
    resp = auth_client.get(reverse("mfa_index"))
    assert "authenticators" in resp.context


def test_add_email_not_allowed(auth_client, user_with_totp):
    resp = auth_client.post(
        reverse("account_email"),
        {"action_add": "", "email": "change-to@this.org"},
    )
    assert resp.status_code == 200
    assert resp.context["form"].errors == {
        "email": [
            "You cannot add an email address to an account protected by two-factor authentication."
        ]
    }

