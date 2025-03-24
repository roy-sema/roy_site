from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Count, F, Max, Q, Sum
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import ngettext
from import_export import fields, resources
from import_export.admin import ExportMixin, ImportExportModelAdmin
from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from compass.integrations.integrations import get_git_providers
from mvp.utils import round_half_up

from .forms import (
    AttestationExportForm,
    ComplianceStandardComponentForm,
    ComplianceStandardForm,
    CustomUserChangeForm,
    CustomUserCreationForm,
    DataProviderForm,
    OrganizationAdminForm,
    RepositoryPullRequestStatusCheckForm,
    SystemMessageForm,
)
from .models import (
    AppComponentVersion,
    Author,
    AuthorGroup,
    AuthorStat,
    ComplianceStandard,
    ComplianceStandardComponent,
    ComplianceStandardReference,
    CustomUser,
    DataProvider,
    DataProviderConnection,
    DataProviderField,
    DataProviderMember,
    DataProviderMemberProjectRecord,
    DataProviderProject,
    DataProviderRecord,
    Geography,
    Industry,
    License,
    Organization,
    ReferenceMetric,
    ReferenceRecord,
    Repository,
    RepositoryAuthor,
    RepositoryCodeAttestation,
    RepositoryCommit,
    RepositoryCommitStatusChoices,
    RepositoryFile,
    RepositoryFileChunk,
    RepositoryFileChunkBlame,
    RepositoryGroup,
    RepositoryPullRequest,
    RepositoryPullRequestStatusCheck,
    Rule,
    RuleCondition,
    ScoreRecord,
    SystemMessage,
    UserInvitation,
    WebhookRequest,
)


def add_user_invites_message(request):
    message_text = "IMPORTANT: To invite users to an existing or new organization, please follow <a href='https://semalab.atlassian.net/wiki/spaces/ACD/pages/2881159174' target='_blank'>this guide</a>."
    if not any(
        message.message == message_text for message in messages.get_messages(request)
    ):
        messages.warning(request, mark_safe(message_text))


@admin.register(AppComponentVersion)
class AppComponentVersionAdmin(admin.ModelAdmin):
    list_display = ("component", "version", "updated_at")


class ComplianceStandardReferenceInline(admin.TabularInline):
    model = ComplianceStandardReference
    extra = 1
    verbose_name = "Reference"
    verbose_name_plural = "References"


class ComplianceStandardResource(resources.ModelResource):
    class Meta:
        model = ComplianceStandard


@admin.register(ComplianceStandard)
class ComplianceStandardAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    change_form_template = "admin/compliancestandard-change-form.html"
    resource_classes = [ComplianceStandardResource]
    form = ComplianceStandardForm
    inlines = [ComplianceStandardReferenceInline]
    list_display = ("name", "status", "num_refs")
    search_fields = ("name", "external_id")
    list_filter = ("risk_level", "ai_usage", "status", "source")
    filter_horizontal = ("geographies", "ai_usage")

    class Media:
        js = ("js/admin/many-to-many-fields.js",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("references")

    def num_refs(self, obj):
        count = obj.references.count()
        if not count:
            return format_html(
                '<span class="errornote">Please add at least one reference</span>'
            )

        return count

    num_refs.short_description = "Num Refs"


class ComplianceStandardComponentResource(resources.ModelResource):
    class Meta:
        model = ComplianceStandardComponent


@admin.register(ComplianceStandardComponent)
class ComplianceStandardComponentAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    resource_classes = [ComplianceStandardComponentResource]
    form = ComplianceStandardComponentForm
    list_display = ("standard", "name", "display_ai_types_list", "rule_list")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("rules")

    def display_ai_types_list(self, obj):
        return obj.get_ai_types_list()

    display_ai_types_list.short_description = "AI Types"

    def rule_list(self, obj):
        rules = obj.rules.all().order_by("name")
        if not rules:
            return "None"

        return format_html(
            '<ul style="padding:0">'
            + "".join([f"<li>{escape(rule)}</li>" for rule in rules])
            + "</ul>"
        )

    rule_list.short_description = "Rules"


class ComplianceStandardReferenceResource(resources.ModelResource):
    class Meta:
        model = ComplianceStandardReference


@admin.register(ComplianceStandardReference)
class ComplianceStandardReferenceAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    resource_classes = [ComplianceStandardReferenceResource]
    list_display = ("text", "url")


class RuleConditionInline(admin.TabularInline):
    model = RuleCondition
    extra = 1


class RuleResource(resources.ModelResource):
    class Meta:
        model = Rule


@admin.register(Rule)
class RuleAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    resource_classes = [RuleResource]
    inlines = [RuleConditionInline]
    list_display = (
        "name",
        "is_preset",
        "organization",
        "apply_organization",
        "condition_mode",
        "conditions",
        "risk",
    )
    list_filter = ["organization__name"]

    class Media:
        js = ("js/admin/many-to-many-fields.js",)

    def get_queryset(self, request):
        return (
            super().get_queryset(request).prefetch_related("conditions", "organization")
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization":
            kwargs["queryset"] = Organization.objects.order_by("name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def conditions(self, obj):
        conditions = obj.conditions.all()
        if not conditions:
            return format_html(
                '<span class="errornote">Please add at least one condition</span>'
            )

        return format_html(
            '<ul style="padding:0">'
            + "".join([f"<li>{escape(condition)}</li>" for condition in conditions])
            + "</ul>"
        )

    conditions.short_description = "Conditions"


class RuleConditionResource(resources.ModelResource):
    class Meta:
        model = RuleCondition


@admin.register(RuleCondition)
class RuleConditionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    resource_classes = [RuleConditionResource]
    list_display = ("rule", "__str__")
    list_filter = ["rule__name"]


class CustomUserResource(resources.ModelResource):
    class Meta:
        model = CustomUser
        exclude = ["password"]


@admin.register(CustomUser)
class CustomUserAdmin(ExportMixin, BaseUserAdmin):
    resource_classes = [CustomUserResource]

    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    actions = ["deactivate_users", "activate_users"]

    list_display = [
        "email",
        "display_organizations_list",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "created_at",
    ]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Personal info", {"fields": ["first_name", "last_name"]}),
        (
            "Permissions",
            {
                "fields": [
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "organizations",
                ]
            },
        ),
        (
            "Preferences",
            {
                "fields": [
                    "company_url",
                    "company_number_of_developers",
                    "consent_marketing_notifications",
                    "compass_anomaly_insights_notifications",
                    "compass_summary_insights_notifications",
                ]
            },
        ),
    ]

    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": [
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                    "groups",
                    "organizations",
                ],
            },
        ),
    ]
    search_fields = ["first_name", "last_name", "email"]
    ordering = ["email"]
    filter_horizontal = ["groups", "organizations"]

    def changelist_view(self, request, extra_context=None):
        add_user_invites_message(request)
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related("organizations")

    def display_organizations_list(self, obj):
        # Use pre-fetched data, avoid N+1 queries
        organizations = obj.organizations.all()
        return sorted(organizations, key=lambda o: o.name)

    display_organizations_list.short_description = "Organizations"

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        def clean(self):
            cleaned_data = super(form, self).clean()
            groups = cleaned_data.get("groups")
            if not groups:
                self.add_error("groups", "At least one group must be selected.")
            return cleaned_data

        setattr(form, "clean", clean)

        return form

    def has_add_permission(self, request):
        return False

    @admin.action(description="Deactivate selected custom users")
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            ngettext(
                f"{updated} User was successfully deactivated.",
                f"{updated} Users were successfully deactivated.",
                updated,
            ),
            messages.SUCCESS,
        )

    @admin.action(description="Activate selected custom users")
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            ngettext(
                f"{updated} User was successfully activated.",
                f"{updated} Users were successfully activated.",
                updated,
            ),
            messages.SUCCESS,
        )


@admin.register(UserInvitation)
class UserInvitationAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ("organization", "email", "is_expired", "is_deleted")
    list_filter = ["is_deleted", "organization__name"]
    search_fields = ["email"]

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        add_user_invites_message(request)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(DataProvider)
class DataProviderAdmin(admin.ModelAdmin):
    form = DataProviderForm
    list_display = ("name", "display_modules_list")

    def display_modules_list(self, obj):
        return obj.get_modules_list()

    display_modules_list.short_description = "Modules"


@admin.register(DataProviderConnection)
class DataProviderConnectionAdmin(admin.ModelAdmin):
    list_display = ("organization", "provider", "is_connected")
    list_filter = ["provider", "organization__name"]


@admin.register(DataProviderField)
class DataProviderFieldAdmin(admin.ModelAdmin):
    list_display = ("provider", "name")
    list_filter = ["provider"]


@admin.register(DataProviderMember)
class DataProviderMemberAdmin(admin.ModelAdmin):
    list_display = ("organization", "provider", "name")
    list_filter = ["provider", "organization__name"]


@admin.register(DataProviderMemberProjectRecord)
class DataProviderMemberProjectRecordAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "project",
        "field",
        "value",
        "date_time",
    )
    list_filter = ["field__provider", "field", "member", "project"]


@admin.register(DataProviderRecord)
class DataProviderRecordAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "field",
        "value",
        "date_time",
    )
    list_filter = ["field__provider", "field", "project"]


@admin.register(DataProviderProject)
class DataProviderProjectAdmin(admin.ModelAdmin):
    list_display = ("organization", "provider", "name")
    list_filter = ["provider"]


class IndustryResource(resources.ModelResource):
    class Meta:
        model = Industry


@admin.register(Industry)
class IndustryAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    resource_classes = [IndustryResource]
    list_display = ["name", "num_organizations"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("organization_set")


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = ("slug", "short_name", "spdx", "category")
    list_filter = ["category"]


@admin.register(Organization)
class OrganizationAdmin(ExportMixin, admin.ModelAdmin):
    change_list_template = "admin/organization-changelist.html"
    form = OrganizationAdminForm
    list_display = (
        "id",
        "public_id",
        "name",
        "status_check_enabled",
        "contextualization_enabled",
        "marked_for_deletion",
        "limits",
        "created_at",
    )
    filter_horizontal = ("geographies",)
    search_fields = ["name"]
    ordering = ("-marked_for_deletion", "-id")
    actions = ["mark_for_deletion", "unmark_for_deletion"]

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark for deletion")
    def mark_for_deletion(self, request, queryset):
        updated = queryset.update(marked_for_deletion=True)
        self.message_user(
            request,
            ngettext(
                f"{updated} Organization was successfully marked for deletion.",
                f"{updated} Organizations were successfully marked for deletion.",
                updated,
            ),
            messages.WARNING,
        )

    @admin.action(description="Unmark for deletion")
    def unmark_for_deletion(self, request, queryset):
        updated = queryset.update(marked_for_deletion=False)
        self.message_user(
            request,
            ngettext(
                f"{updated} Organization was successfully unmarked for deletion.",
                f"{updated} Organizations were successfully unmarked for deletion.",
                updated,
            ),
            messages.SUCCESS,
        )

    def public_id(self, obj):
        return obj.public_id()

    def limits(self, obj):
        scans = obj.analysis_max_scans
        repos = obj.analysis_max_repositories
        lines = obj.analysis_max_lines_per_repository
        if not scans and not repos and not lines:
            return "No limits"

        return f"Scans: {scans} · Repos: {repos} · Lines: {lines}"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related("industry")

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "organization-usage/",
                self.organization_usage_view,
                name="organization-usage",
            ),
        ]
        return my_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["custom_view_url"] = reverse("admin:organization-usage")
        add_user_invites_message(request)
        return super().changelist_view(request, extra_context=extra_context)

    # NOTE: this methods creates N+1 queries, but we are fine with it since it's for
    #       internal reporting purposes and not used that frequently anyway
    @method_decorator(staff_member_required)
    def organization_usage_view(self, request):
        organizations = (
            Organization.objects.all()
            .annotate(
                repo_count=Count("repository", distinct=True),
                pr_count=Count("repository__repositorypullrequest", distinct=True),
                full_scan_count=Count(
                    "repository__repositorycommit",
                    filter=Q(
                        repository__repositorycommit__status=RepositoryCommitStatusChoices.ANALYZED,
                        repository__repositorycommit__pull_requests__isnull=True,
                    ),
                    distinct=True,
                ),
                last_scan_date=Max("repository__repositorycommit__date_time"),
            )
            .order_by("name")
        )

        line_counts = RepositoryFile.objects.values(
            organization_id=F("commit__repository__organization_id")
        ).annotate(
            num_lines=Sum("code_num_lines"),
            ai_num_lines=Sum("code_ai_num_lines"),
            ai_pure_num_lines=Sum("code_ai_pure_num_lines"),
            ai_blended_num_lines=Sum("code_ai_blended_num_lines"),
        )
        lines_by_org = {
            line_count["organization_id"]: line_count for line_count in line_counts
        }

        rows = []
        for organization in organizations:
            connected_tools = DataProviderConnection.objects.filter(
                organization=organization
            )
            tools = (
                ", ".join(connection.provider.name for connection in connected_tools)
                if connected_tools
                else None
            )
            num_users = CustomUser.objects.filter(organizations=organization).count()
            last_login_user = (
                CustomUser.objects.filter(
                    organizations=organization, last_login__isnull=False
                )
                .order_by("-last_login")
                .first()
            )
            last_login = None
            if last_login_user:
                last_login = (
                    last_login_user.last_login.strftime("%Y-%m-%d")
                    + f" ({last_login_user.username})"
                )

            num_decimals = 2
            percentages = None
            if organization.pk in lines_by_org:
                overall = round_half_up(
                    lines_by_org[organization.pk]["ai_num_lines"]
                    / lines_by_org[organization.pk]["num_lines"]
                    * 100,
                    num_decimals,
                )
                blended = round_half_up(
                    lines_by_org[organization.pk]["ai_pure_num_lines"]
                    / lines_by_org[organization.pk]["num_lines"]
                    * 100,
                    num_decimals,
                )
                pure = round_half_up(overall - blended, num_decimals)
                percentages = {"overall": overall, "blended": blended, "pure": pure}

            rows.append(
                {
                    "organization": organization.name,
                    "connected_tools": tools,
                    "repo_count": organization.repo_count,
                    "pr_count": organization.pr_count,
                    "full_scan_count": organization.full_scan_count,
                    "last_scan_date": organization.last_scan_date,
                    "num_users": num_users,
                    "last_login": last_login,
                    "percentages": percentages,
                }
            )
        context = dict(
            self.admin_site.each_context(request),
            rows=rows,
        )
        return render(request, "admin/organization-usage.html", context)


@admin.register(ReferenceMetric)
class ReferenceMetricAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "metric",
        "percentile",
        "segment",
        "value",
    )


@admin.register(ReferenceRecord)
class ReferenceRecordAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "org_id",
        "org_name",
        "segment",
        "code_low_risk",
        "code_medium_risk",
        "code_high_risk",
        "commit_change_rate",
        "development_activity_change_rate",
        "open_source_medium_high_file_count",
        "open_source_medium_high_package_count",
        "cve_high_risk",
        "cyber_security_high_risk",
    )


@admin.register(ScoreRecord)
class ScoreRecordAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "date_time",
        "sema_score",
        "product_score",
        "compliance_score",
    )


class GitProviderFilter(SimpleListFilter):
    title = "provider"
    parameter_name = "provider__name"

    def lookups(self, request, model_admin):
        return [(provider.name, provider.name) for provider in get_git_providers()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.parameter_name: self.value()})
        else:
            return queryset


class RepositoryGitProviderFilter(GitProviderFilter):
    parameter_name = "repository__" + GitProviderFilter.parameter_name


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "public_id",
        "owner",
        "name",
        "view_in_dashboard",
        "provider",
        "organization",
        "code_ai_percentage",
        "code_ai_blended_percentage",
        "code_ai_pure_percentage",
        "last_commit_sha",
        "last_analysis_file",
    )
    list_filter = [GitProviderFilter, "organization__name"]
    ordering = ["organization__name"]
    search_fields = ["name", "owner", "last_commit_sha"]

    def get_queryset(self, request):
        return (
            super().get_queryset(request).prefetch_related("organization", "provider")
        )

    def view_in_dashboard(self, obj):
        url = reverse("repository_detail", kwargs={"pk_encoded": obj.public_id()})

        return format_html(
            f"<a href='{url}' target='_blank'>"
            + "<img src='/static/admin/img/icon-viewlink.svg' />"
            + "</a>"
        )

    view_in_dashboard.short_description = "View"


@admin.register(RepositoryPullRequest)
class RepositoryPullRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "repository",
        "pr_number",
        "view_in_dashboard",
        "provider",
        "organization",
        "is_closed",
        "analysis_status",
        "base_commit_sha",
        "head_commit_sha",
        "code_ai_percentage",
        "code_ai_blended_percentage",
        "code_ai_pure_percentage",
        "created_at",
        "updated_at",
    )
    list_filter = [
        RepositoryGitProviderFilter,
        "is_closed",
        "repository__organization__name",
        "repository__name",
    ]
    ordering = ["-updated_at"]
    search_fields = [
        "repository__name",
        "pr_number",
        "base_commit_sha",
        "head_commit_sha",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._head_commit_map = {}

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .prefetch_related("repository", "repository__provider")
        )

        head_commit_shas = queryset.values_list("head_commit_sha", flat=True)
        head_commits = RepositoryCommit.objects.filter(sha__in=head_commit_shas)

        self._head_commit_map = {commit.sha: commit for commit in head_commits}

        return queryset

    def analysis_status(self, obj):
        commit = self._head_commit_map.get(obj.head_commit_sha)
        return commit.get_status_display() if commit else None

    def provider(self, obj):
        return obj.repository.provider.name

    def organization(self, obj):
        return obj.repository.organization.name

    def view_in_dashboard(self, obj):
        url = reverse(
            "pull_request_scan",
            kwargs={
                "external_id": obj.repository.external_id,
                "pr_number": obj.pr_number,
            },
        )

        return format_html(
            f"<a href='{url}' target='_blank'>"
            + "<img src='/static/admin/img/icon-viewlink.svg' />"
            + "</a>"
        )

    view_in_dashboard.short_description = "View"


@admin.register(RepositoryPullRequestStatusCheck)
class RepositoryPullRequestStatusCheckAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "get_repository",
        "get_pr_number",
        "get_organization",
        "status_check_id",
        "status",
        "created_at",
    )
    list_filter = ["status", "pull_request__repository__organization"]
    search_fields = [
        "pull_request__pr_number",
        "pull_request__repository__name",
        "status_check_id",
    ]
    form = RepositoryPullRequestStatusCheckForm

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                "pull_request",
                "pull_request__repository",
                "pull_request__repository__organization",
            )
        )

    def get_repository(self, obj):
        return obj.pull_request.repository.name

    def get_pr_number(self, obj):
        return obj.pull_request.pr_number

    def get_organization(self, obj):
        return obj.pull_request.repository.organization.name

    get_repository.short_description = "Repository"
    get_pr_number.short_description = "PR Number"
    get_organization.short_description = "Organization"


class IsPullRequestFilter(admin.SimpleListFilter):
    title = "Is pull request"
    parameter_name = "is_pull_request"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(pull_requests__isnull=False).distinct()
        if self.value() == "no":
            return queryset.filter(pull_requests__isnull=True).distinct()
        return queryset


@admin.register(RepositoryCommit)
class RepositoryCommitAdmin(admin.ModelAdmin):
    list_display = (
        "sha",
        "status",
        "repository",
        "is_pull_request",
        "date_time",
        "code_num_lines",
        "code_ai_percentage",
        "code_ai_blended_percentage",
        "code_ai_pure_percentage",
        "not_evaluated_num_files",
        "analysis_file",
    )
    list_filter = [
        "status",
        IsPullRequestFilter,
        "repository__name",
        "repository__organization__name",
    ]
    search_fields = ["sha"]
    readonly_fields = ["pull_requests"]  # otherwise the page doesn't load on prod


@admin.register(RepositoryFile)
class RepositoryFileAdmin(admin.ModelAdmin):
    list_display = (
        "file_path",
        "commit",
        "get_repository_name",
        "get_organization_name",
    )
    list_filter = ["commit__repository__name"]
    ordering = ["-updated_at"]
    search_fields = ["file_path"]

    def get_repository_name(self, obj):
        return obj.commit.repository.name

    def get_organization_name(self, obj):
        return obj.commit.repository.organization.name

    get_repository_name.short_description = "Repository"
    get_organization_name.short_description = "Organization"


class RepositoryCodeAttestationResource(resources.ModelResource):
    file_path = fields.Field(column_name="files_paths (beta)")
    original_label = fields.Field(column_name="original_labels")

    def __init__(self, **kwargs):
        super().__init__()
        self.org_id = kwargs.get("org_id")

    def dehydrate_file_path(self, obj):
        try:
            file_chunks = (
                RepositoryFileChunk.objects.filter(
                    code_hash=obj.code_hash, file__commit__repository=obj.repository
                )
                .distinct()
                .prefetch_related("file")
            )
            return "; ".join(file_chunks.values_list("file__file_path", flat=True))
        except Exception:
            return ""

    def dehydrate_original_label(self, obj):
        try:
            file_chunks = RepositoryFileChunk.objects.filter(
                code_hash=obj.code_hash, file__commit__repository=obj.repository
            ).distinct()
            return "; ".join(
                file_chunks.values_list("code_generation_label", flat=True)
            )
        except Exception:
            return ""

    def filter_export(self, queryset, *args, **kwargs):
        if self.org_id:
            return queryset.filter(repository__organization=self.org_id)
        return queryset

    class Meta:
        model = RepositoryCodeAttestation
        fields = (
            "repository__organization__name",
            "repository",
            "repository__owner",
            "repository__name",
            "file_path",
            "code_hash",
            "original_label",
            "label",
            "attested_by__email",
            "updated_at",
        )


@admin.register(RepositoryCodeAttestation)
class RepositoryCodeAttestationAdmin(ExportMixin, admin.ModelAdmin):
    list_display = (
        "repository",
        "code_hash",
        "label",
        "attested_by",
        "updated_at",
    )
    list_filter = ["repository__name", "label"]
    ordering = ["-updated_at"]
    search_fields = ["code_hash"]
    resource_class = RepositoryCodeAttestationResource
    export_form_class = AttestationExportForm

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("attested_by")

    def get_export_resource_kwargs(self, request, *args, **kwargs):
        export_form = kwargs.get("export_form")
        if export_form:
            organization = export_form.cleaned_data.get("organization")
            if organization:
                return {"org_id": organization.id}
        return {}


@admin.register(RepositoryFileChunk)
class RepositoryFileChunkAdmin(admin.ModelAdmin):
    list_display = (
        "file",
        "code_hash",
        "code_line_start",
        "code_line_end",
        "code_generation_label",
        "code_generation_score",
    )
    list_filter = ["code_generation_label", "file__commit__repository__name"]
    ordering = ["-updated_at"]
    search_fields = ["code_hash", "file__file_path"]

    # The dropdowns are too long to be useful and cause slow queries
    readonly_fields = ["file"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("file")


@admin.register(RepositoryFileChunkBlame)
class RepositoryFileChunkBlameAdmin(admin.ModelAdmin):
    list_display = (
        "chunk",
        "author",
        "sha",
        "date_time",
        "code_line_start",
        "code_line_end",
        "code_generation_label",
    )
    list_filter = ["code_generation_label", "chunk__file__commit__repository__name"]
    search_fields = ["chunk__code_hash", "author__name", "sha"]

    # The dropdowns are too long to be useful and cause slow queries
    readonly_fields = ["chunk", "author"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("author")


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("organization", "name", "email", "login", "external_id")
    list_filter = ["organization__name"]
    search_fields = ["name", "email", "login", "external_id"]


@admin.register(AuthorGroup)
class AuthorGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "team_type", "developer_type")
    list_filter = ["organization__name"]


@admin.register(RepositoryAuthor)
class RepositoryAuthorAdmin(admin.ModelAdmin):
    list_display = (
        "repository",
        "author",
        "code_ai_percentage",
        "code_ai_blended_percentage",
        "code_ai_pure_percentage",
    )
    list_filter = ["repository__name"]


@admin.register(RepositoryGroup)
class RepositoryGroupAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "usage_category",
    )
    list_filter = ["organization__name"]


@admin.register(Geography)
class GeographyAdmin(TreeAdmin):
    orm = movenodeform_factory(Geography)
    list_display = ("name", "code")
    search_fields = ("name", "code")
    readonly_fields = ("path", "depth", "numchild", "full_path", "parent")

    def full_path(self, obj):
        return obj.get_full_path()

    def parent(self, obj):
        return mark_safe(
            '<a href="{}">{}</a>'.format(
                reverse("admin:mvp_geography_change", args=(obj.get_parent().pk,)),
                obj.get_parent(),
            )
        )


@admin.register(SystemMessage)
class SystemMessageAdmin(admin.ModelAdmin):
    form = SystemMessageForm

    list_display = (
        "id",
        "text",
        "is_showing",
        "starts_at",
        "expires_at",
        "is_dismissible",
    )
    list_filter = ["starts_at", "expires_at", "is_dismissible"]
    ordering = ["-starts_at"]
    fieldsets = [
        ("Dates", {"fields": ["starts_at", "expires_at"]}),
        ("Message", {"fields": ["text", "read_more_link", "is_dismissible"]}),
    ]


@admin.register(WebhookRequest)
class WebhookRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "response_status_code",
        "response_message",
        "data_file_path",
        "created_at",
    )
    list_filter = ["provider__name"]
    search_fields = ["provider__name"]
    ordering = ["-created_at"]


@admin.register(AuthorStat)
class AuthorStatAdmin(admin.ModelAdmin):
    list_display = (
        "time",
        "author",
        "repository",
        "commit",
        "code_ai_num_lines",
        "code_ai_blended_num_lines",
        "code_ai_pure_num_lines",
        "code_not_ai_num_lines",
    )
    search_fields = ("author__name", "repository__name", "commit__sha")
    list_filter = ("repository__organization",)

