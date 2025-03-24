import json
from urllib.parse import unquote

import posthog
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.urls import resolve
from sentry_sdk import capture_exception, capture_message, push_scope, set_user

from mvp.models import Organization


class ClearCookiesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "reset_cookies", False):
            response.delete_cookie("feedback-banner-dismissed")
        return response


class CurrentOrganizationMiddleware:
    KEY_CURRENT_ORGANIZATION = "current_organization_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user_organizations = None
        request.current_organization = None

        user = request.user
        if not user.is_authenticated:
            return self.get_response(request)

        url_name = resolve(request.path_info).url_name
        if url_name == "account_logout":
            return self.get_response(request)

        organizations = self.get_user_organizations(request)
        if not organizations:
            capture_message("User has no organizations", level="error")
            return render(request, "custom_errors/no_organizations.html")

        request.user_organizations = organizations
        request.user_organizations_public_map = {
            org.public_id(): org.name for org in organizations
        }
        current_org = self.get_current_organization(request)
        if current_org:
            self.set_current_organization(request, current_org)

        return self.get_response(request)

    def get_user_organizations(self, request):
        user = request.user
        qs = Organization.objects if user.is_superuser else user.organizations
        return qs.order_by(Lower("name")).all()

    def get_current_organization(self, request):
        user = request.user
        if not user.is_authenticated:
            return None

        session_org_id = request.session.get(self.KEY_CURRENT_ORGANIZATION)
        if session_org_id:
            try:
                return request.user_organizations.get(id=session_org_id)
            except Organization.DoesNotExist as error:
                with push_scope() as scope:
                    scope.set_extra("session_org_id", session_org_id)
                    capture_exception(error)
                pass

        # by the default use first one associated to the user, not the first one alphabetically
        # TODO: allow user to set default organization
        return request.user.organizations.first()

    @classmethod
    def set_current_organization(cls, request, organization):
        request.session[cls.KEY_CURRENT_ORGANIZATION] = organization.id
        request.current_organization = organization


class MFAMiddleware:
    """
    Inspiration:
    https://github.com/pennersr/django-allauth/discussions/3943#discussioncomment-9980609
    https://github.com/pennersr/django-allauth/issues/3649#issuecomment-2023044039
    """

    allowed_pages = [
        "account_login",
        "account_logout",
        "account_reauthenticate",
        "account_reset_password_done",
        "account_reset_password_from_key",
        "account_reset_password_from_key_done",
        "account_reset_password",
        "account_email",
        "account_email_verification_sent",
        "account_confirm_email",
        "mfa_activate_totp",
        "mfa_index",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def is_allowed_page(self, request) -> bool:
        url_name = resolve(request.path_info).url_name
        return url_name in self.allowed_pages

    def organization_requires_mfa(self, request):
        # If any organization requires MFA, then the user must have MFA enabled
        organizations = request.user_organizations or []
        return any([organization.require_mfa for organization in organizations])

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not self.is_allowed_page(request)
            and self.organization_requires_mfa(request)
            and not is_mfa_enabled(request.user)
        ):
            return redirect("mfa_activate_totp")

        response = self.get_response(request)
        return response


class PostHogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.POSTHOG_PROJECT_API_KEY = settings.POSTHOG_PROJECT_API_KEY
        request.POSTHOG_INSTANCE_ADDRESS = settings.POSTHOG_INSTANCE_ADDRESS

        response = self.reset_on_logout(request)
        return response

    def connect_backend_frontend_identities(self, request):
        posthog_cookie = request.COOKIES.get(f"ph_{posthog.project_api_key}_posthog")
        if posthog_cookie and request.user.is_authenticated:
            cookie_dict = json.loads(unquote(posthog_cookie))
            if cookie_dict.get("distinct_id"):
                posthog.alias(cookie_dict["distinct_id"], request.user.email)

    def reset_on_logout(self, request):
        response = self.get_response(request)
        try:
            url_name = resolve(request.path_info).url_name
            if url_name == "account_logout":
                response.set_cookie("logged_out", "true", max_age=10)
        except Exception:
            pass

        return response


class SentryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            set_user({"email": request.user.email})

        return self.get_response(request)

