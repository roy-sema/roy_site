import base64
import json

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import FileField
from django.db.models.fields import (
    BinaryField,
    DateField,
    DateTimeField,
    TimeField,
)
from django.utils import dateparse
from django.utils.encoding import force_bytes, force_str


SERIALIZED_DB_FIELD_PREFIX = "_db_"


def serialize_instance(instance):
    """
    Since Django 1.6 items added to the session are no longer pickled,
    but JSON encoded by default. We are storing partially complete models
    in the session (user, account, token, ...). We cannot use standard
    Django serialization, as these are models are not "complete" yet.
    Serialization will start complaining about missing relations et al.
    """
    data = {}
    for k, v in instance.__dict__.items():
        if k.startswith("_") or callable(v):
            continue
        try:
            field = instance._meta.get_field(k)
            if isinstance(field, BinaryField):
                if v is not None:
                    v = force_str(base64.b64encode(v))
            elif isinstance(field, FileField):
                if v and not isinstance(v, str):
                    v = {
                        "name": v.name,
                        "content": base64.b64encode(v.read()).decode("ascii"),
                    }
            # Check if the field is serializable. If not, we'll fall back
            # to serializing the DB values which should cover most use cases.
            try:
                json.dumps(v, cls=DjangoJSONEncoder)
            except TypeError:
                v = field.get_prep_value(v)
                k = SERIALIZED_DB_FIELD_PREFIX + k
        except FieldDoesNotExist:
            pass
        data[k] = v
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def deserialize_instance(model, data):
    ret = model()
    for k, v in data.items():
        is_db_value = False
        if k.startswith(SERIALIZED_DB_FIELD_PREFIX):
            k = k[len(SERIALIZED_DB_FIELD_PREFIX) :]
            is_db_value = True
        if v is not None:
            try:
                f = model._meta.get_field(k)
                if isinstance(f, DateTimeField):
                    v = dateparse.parse_datetime(v)
                elif isinstance(f, TimeField):
                    v = dateparse.parse_time(v)
                elif isinstance(f, DateField):
                    v = dateparse.parse_date(v)
                elif isinstance(f, BinaryField):
                    v = force_bytes(base64.b64decode(force_bytes(v)))
                elif isinstance(f, FileField):
                    if isinstance(v, dict):
                        v = ContentFile(base64.b64decode(v["content"]), name=v["name"])
                elif is_db_value:
                    try:
                        # This is quite an ugly hack, but will cover most
                        # use cases...
                        # The signature of `from_db_value` changed in Django 3
                        # https://docs.djangoproject.com/en/3.0/releases/3.0/#features-removed-in-3-0
                        v = f.from_db_value(v, None, None)
                    except Exception:
                        raise ImproperlyConfigured(
                            "Unable to auto serialize field '{}', custom"
                            " serialization override required".format(k)
                        )
            except FieldDoesNotExist:
                pass
        setattr(ret, k, v)
    return ret


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


authenticate = AuthenticateView.as_view()


@method_decorator(login_required, name="dispatch")
class ReauthenticateView(BaseReauthenticateView):
    form_class = ReauthenticateForm
    template_name = "mfa/reauthenticate." + account_settings.TEMPLATE_EXTENSION

    def get_form_kwargs(self):
        ret = super().get_form_kwargs()
        ret["user"] = self.request.user
        return ret

    def get_form_class(self):
        return get_form_class(app_settings.FORMS, "reauthenticate", self.form_class)

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


reauthenticate = ReauthenticateView.as_view()


@method_decorator(login_required, name="dispatch")
class IndexView(TemplateView):
    template_name = "mfa/index." + account_settings.TEMPLATE_EXTENSION

    def get_context_data(self, **kwargs):
        ret = super().get_context_data(**kwargs)
        authenticators = {}
        for auth in Authenticator.objects.filter(user=self.request.user):
            if auth.type == Authenticator.Type.WEBAUTHN:
                auths = authenticators.setdefault(auth.type, [])
                auths.append(auth.wrap())
            else:
                authenticators[auth.type] = auth.wrap()
        ret["authenticators"] = authenticators
        ret["MFA_SUPPORTED_TYPES"] = app_settings.SUPPORTED_TYPES
        ret["is_mfa_enabled"] = is_mfa_enabled(self.request.user)
        return ret


index = IndexView.as_view()

