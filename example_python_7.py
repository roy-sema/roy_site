from django.core.checks import Critical, register


@register()
def settings_check(app_configs, **kwargs):
    from allauth.account import app_settings as account_settings
    from allauth.mfa import app_settings
    from allauth.mfa.models import Authenticator

    ret = []
    if app_settings.PASSKEY_SIGNUP_ENABLED:
        if Authenticator.Type.WEBAUTHN not in app_settings.SUPPORTED_TYPES:
            ret.append(
                Critical(
                    msg="MFA_PASSKEY_SIGNUP_ENABLED requires MFA_SUPPORTED_TYPES to include 'webauthn'"
                )
            )
        if not account_settings.EMAIL_VERIFICATION_BY_CODE_ENABLED:
            # The fact that a signup is passkey based is stored in the session,
            # which gets lost when using link based verification.
            ret.append(
                Critical(
                    msg="MFA_PASSKEY_SIGNUP_ENABLED requires ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED"
                )
            )
        email_required = account_settings.SIGNUP_FIELDS.get("email", {}).get("required")
        if not email_required:
            ret.append(
                Critical(
                    msg="MFA_PASSKEY_SIGNUP_ENABLED requires ACCOUNT_SIGNUP_FIELDS to contain 'email*'"
                )
            )
        if (
            account_settings.EMAIL_VERIFICATION
            != account_settings.EmailVerificationMethod.MANDATORY
        ):
            ret.append(
                Critical(
                    msg="MFA_PASSKEY_SIGNUP_ENABLED requires ACCOUNT_EMAIL_VERIFICATION = 'mandatory'"
                )
            )
    return ret

from unittest.mock import Mock

from django.contrib.auth.models import AnonymousUser
from django.test.utils import override_settings

import pytest

from allauth.usersessions.middleware import UserSessionsMiddleware
from allauth.usersessions.models import UserSession
from allauth.usersessions.signals import session_client_changed


def test_mw_without_request_user(rf, db, settings):
    settings.USERSESSIONS_TRACK_ACTIVITY = True
    mw = UserSessionsMiddleware(lambda request: None)
    request = rf.get("/")
    mw(request)
    assert UserSession.objects.count() == 0


@pytest.mark.parametrize("track_activity", [False, True])
def test_mw_with_request_user(rf, db, settings, user, track_activity):
    settings.USERSESSIONS_TRACK_ACTIVITY = track_activity
    mw = UserSessionsMiddleware(lambda request: None)
    request = rf.get("/")
    request.user = user
    request.session = Mock()
    request.session.session_key = "sess-123"
    mw(request)
    assert (
        UserSession.objects.filter(session_key="sess-123", user=user).exists()
        is track_activity
    )


def test_mw_with_anonymous_request_user(rf, db, settings):
    settings.USERSESSIONS_TRACK_ACTIVITY = True
    mw = UserSessionsMiddleware(lambda request: None)
    request = rf.get("/")
    request.user = AnonymousUser()
    request.session = Mock()
    request.session.session_key = "sess-123"
    mw(request)
    assert not UserSession.objects.exists()


@override_settings(USERSESSIONS_TRACK_ACTIVITY=True)
def test_mw_change_ip_and_useragent(rf, db, user):
    mw = UserSessionsMiddleware(lambda request: None)

    # First request
    request1 = rf.get("/")
    request1.user = user
    request1.session = Mock()
    request1.session.session_key = "sess-123"
    request1.META["HTTP_USER_AGENT"] = "Old User Agent"
    request1.META["REMOTE_ADDR"] = "1.1.1.1"
    mw(request1)

    # Second request with changed IP and User Agent
    request2 = rf.get("/")
    request2.user = user
    request2.session = Mock()
    request2.session.session_key = "sess-123"
    request2.META["HTTP_USER_AGENT"] = "New User Agent"
    request2.META["REMOTE_ADDR"] = "2.2.2.2"

    # Set up signal receiver
    signal_received = []

    def signal_handler(sender, request, from_session, to_session, **kwargs):
        signal_received.append((from_session, to_session))

    session_client_changed.connect(signal_handler)

    # Process second request
    mw(request2)

    # Check if UserSession was updated
    user_session = UserSession.objects.get(session_key="sess-123", user=user)
    assert user_session.ip == "2.2.2.2"
    assert user_session.user_agent == "New User Agent"

    # Check if signal was triggered
    assert len(signal_received) == 1
    from_session, to_session = signal_received[0]
    assert from_session.ip == "1.1.1.1"
    assert from_session.user_agent == "Old User Agent"
    assert to_session.ip == "2.2.2.2"
    assert to_session.user_agent == "New User Agent"

    # Clean up signal connection
    session_client_changed.disconnect(signal_handler)

