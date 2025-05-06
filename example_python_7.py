import json

import markdown
from allauth.account.forms import ResetPasswordKeyForm
from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.forms import inlineformset_factory
from import_export.forms import ExportForm

from .mixins import DecodePublicIdMixin
from .models import (
    AITypeChoices,
    AuthorGroup,
    ComplianceStandard,
    ComplianceStandardComponent,
    CustomUser,
    DataProvider,
    DataProviderConnection,
    DataProviderProject,
    Geography,
    Industry,
    ModuleChoices,
    Organization,
    ProductivityImprovementChoices,
    RepositoryGroup,
    RepositoryPullRequestStatusCheck,
    Rule,
    RuleCondition,
    SystemMessage,
    UserInvitation,
)


class PrettyJSONEncoder(json.JSONEncoder):
    def __init__(self, *args, indent, sort_keys, **kwargs):
        super().__init__(*args, indent=2, sort_keys=True, **kwargs)


class ComplianceStandardForm(forms.ModelForm):
    class Meta:
        model = ComplianceStandard
        fields = "__all__"

    industries = forms.ModelMultipleChoiceField(
        queryset=Industry.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        help_text=f"NOTE: Leave all unchecked for '{Industry.LABEL_NONE}'",
        required=False,
    )

    def clean_industries(self):
        industries = self.cleaned_data.get("industries")
        if (
            industries is not None
            and industries.filter(name="To be determined").exists()
            and industries.count() > 1
        ):
            raise ValidationError(
                "'To be determined' cannot be used with other industries."
            )
        return industries


class ComplianceStandardComponentForm(forms.ModelForm):
    ai_types = forms.MultipleChoiceField(
        choices=AITypeChoices.choices,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ComplianceStandardComponent
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super(ComplianceStandardComponentForm, self).__init__(*args, **kwargs)
        rules = Rule.objects.all().order_by("name")

        self.fields["rules"].queryset = rules


class InviteUserForm(forms.ModelForm):
    """
    A form for creating new users when invited.
    Includes a repeated password and accept terms field.
    """

    accept_terms = forms.BooleanField(
        label="Accept the Terms & Conditions and Privacy Policy",
        required=True,
    )
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(
        label="Password confirmation", widget=forms.PasswordInput
    )

    class Meta:
        model = CustomUser
        fields = ["email", "first_name", "last_name", "consent_marketing_notifications"]

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        self.instance.set_password(self.cleaned_data["password1"])
        return super().save(commit)


class CustomUserCreationForm(InviteUserForm):
    """
    A form for creating new users. Includes all the required
    fields, plus a repeated password, accept terms field and
    additonal fields to create the organization.
    """

    organization_name = forms.CharField(max_length=100, required=True)

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "first_name",
            "last_name",
            "organization_name",
            "consent_marketing_notifications",
        ]


class CustomUserChangeForm(forms.ModelForm):
    """
    A form for updating users. Includes all the fields on
    the user, but replaces the password field with admin's
    disabled password hash display field.
    """

    password = ReadOnlyPasswordHashField()

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "password",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
        ]

