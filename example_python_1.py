import os
from dataclasses import asdict
from decimal import Decimal

from rest_framework import serializers

from .mixins import PublicIdMixin
from .models import (
    Author,
    AuthorGroup,
    CustomUser,
    Repository,
    RepositoryCodeAttestation,
    RepositoryCommit,
    RepositoryFile,
    RepositoryFileChunk,
    RepositoryFileChunkBlame,
    RepositoryGroup,
    RepositoryPullRequest,
    Rule,
    RuleCondition,
)
from .services import RuleService


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name")

    class Meta:
        model = CustomUser
        fields = ["public_id", "full_name", "email"]


class RepositoryCommitSerializer(serializers.ModelSerializer):
    attested_num_lines = serializers.SerializerMethodField()

    class Meta:
        model = RepositoryCommit
        fields = [
            "sha",
            "date_time",
            "analysis_num_files",
            "not_evaluated_num_files",
            "attested_num_lines",
            "languages",
            "language_list_str",
            "total_num_lines",
            "percentage_ai_overall",
            "percentage_ai_pure",
            "percentage_ai_blended",
            "percentage_human",
            "code_num_lines",
        ]

    def get_attested_num_lines(self, obj):
        if self.context.get("with_attestation_data", False):
            return obj.get_attested_num_lines(self.context.get("num_lines_by_sha"))
        return None


class RepositorySerializer(PublicIdMixin, serializers.ModelSerializer):
    attested_num_lines = serializers.SerializerMethodField()
    until_commit = serializers.SerializerMethodField()

    class Meta:
        model = Repository
        fields = [
            "public_id",
            "full_name",
            "last_analysis_num_files",
            "not_evaluated_num_files",
            "attested_num_lines",
            "until_commit",
            "code_num_lines",
            "languages",
            "language_list_str",
            "total_num_lines",
            "percentage_ai_overall",
            "percentage_ai_pure",
            "percentage_ai_blended",
            "percentage_human",
        ]

    def get_attested_num_lines(self, obj):
        if self.context.get("with_attestation_data", False):
            return obj.get_attested_num_lines(self.context.get("num_lines_by_sha"))
        return None

    def get_until_commit(self, obj):
        until_commit = (getattr(obj, "until_commit", [None]) or [None])[-1]
        if until_commit:
            return RepositoryCommitSerializer(until_commit, context=self.context).data
        return None


class RepositoryCodeAttestationSerializer(PublicIdMixin, serializers.ModelSerializer):
    attested_by = UserSerializer(read_only=True)

    class Meta:
        model = RepositoryCodeAttestation
        fields = [
            "public_id",
            "code_hash",
            "label",
            "comment",
            "attested_by",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "attested_by",
            "updated_at",
        ]


class RepositoryFileChunkBlameSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = RepositoryFileChunkBlame
        fields = ["author", "code_line_start", "code_line_end"]

    def get_author(self, obj):
        return obj.author.name


class RepositoryFileChunkBlameExraDataSerializer(RepositoryFileChunkBlameSerializer):
    class Meta:
        model = RepositoryFileChunkBlame
        fields = [
            "author",
            "code_line_start",
            "code_line_end",
            "sha",
            "date_time",
            "code_generation_label",
        ]


class RepositoryFileChunkSerializer(serializers.ModelSerializer):
    is_not_evaluated = serializers.BooleanField()
    code = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    attestation = RepositoryCodeAttestationSerializer()
    blames = serializers.SerializerMethodField()

    class Meta:
        model = RepositoryFileChunk
        fields = [
            "name",
            "label",
            "is_not_evaluated",
            "code_line_start",
            "code_line_end",
            "code",
            "code_hash",
            "public_id",
            "attestation",
            "blames",
        ]

    def get_blames(self, obj):
        serializer_class = (
            RepositoryFileChunkBlameExraDataSerializer
            if self.context.get("extraData")
            else RepositoryFileChunkBlameSerializer
        )
        serializer = serializer_class(
            obj.repositoryfilechunkblame_set, many=True, context=self.context
        )
        return serializer.data

    def get_code(self, obj):
        lines = self.context.get("lines", [])
        try:
            return lines[obj.code_line_start - 1 : obj.code_line_end]
        except IndexError:
            return []

    def get_label(self, obj):
        return obj.get_label()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["blames"] = sorted(data["blames"], key=lambda x: x["code_line_start"])
        return data


class RepositoryFileSerializer(serializers.ModelSerializer):
    chunks = serializers.SerializerMethodField()
    relative_path = serializers.CharField()
    shredded = serializers.SerializerMethodField()

    class Meta:
        model = RepositoryFile
        fields = [
            "file_path",
            "chunks",
            "not_evaluated",
            "chunks_ai_blended",
            "chunks_ai_pure",
            "chunks_human",
            "chunks_not_evaluated",
            "chunks_attested",
            "public_id",
            "relative_path",
            "shredded",
        ]

    def load_file_lines(self, file_path):
        if not os.path.exists(file_path):
            return []

        with open(file_path, "r", errors="replace") as code_file:
            return code_file.readlines()

    def get_chunks(self, obj):
        commit = self.context.get("commit", None)
        hydrated = self.context.get("hydrated", False)
        extraData = self.context.get("extraData", False)

        if not hydrated:
            return []

        if commit and not obj.not_evaluated:
            folder_path = commit.analysis_folder()
            file_path = os.path.join(folder_path, obj.relative_path)
            lines = self.load_file_lines(file_path) if not commit.shredded else []
            chunks = obj.chunk_list()
            return RepositoryFileChunkSerializer(
                chunks,
                many=True,
                context={
                    "lines": lines,
                    "shredded": commit.shredded,
                    "extraData": extraData,
                },
            ).data

        return []

    def get_shredded(self, obj):
        commit = self.context.get("commit", None)
        return commit.shredded if commit else False


class RepositoryPullRequestSerializer(PublicIdMixin, serializers.ModelSerializer):
    repository = RepositorySerializer(read_only=True)

    class Meta:
        model = RepositoryPullRequest
        fields = [
            "pr_number",
            "head_commit_sha",
            "analysis_num_files",
            "not_evaluated_num_files",
            "repository",
            "updated_at",
            "needs_composition_recalculation",
            "is_closed",
        ]


class RuleConditionSerializer(PublicIdMixin, serializers.ModelSerializer):
    condition_str = serializers.SerializerMethodField()

    class Meta:
        model = RuleCondition
        fields = [
            "public_id",
            "code_type",
            "operator",
            "percentage",
            "condition_str",
        ]

    def get_condition_str(self, obj):
        return str(obj)


class RuleSerializer(PublicIdMixin, serializers.ModelSerializer):
    conditions = RuleConditionSerializer(many=True)

    class Meta:
        model = Rule
        fields = [
            "public_id",
            "name",
            "description",
            "condition_mode",
            "risk",
            "apply_organization",
            "conditions",
            "rule_str",
        ]


# TODO: add proper serializer
def charts_serializer(charts):
    return [asdict(chart) for chart in charts]


def ai_composition_serializer(ai_composition):
    serialized = []

    for ai_type in ai_composition:
        serialized_rules = []
        for rule, color in ai_type["rules"]:
            serialized_rule = RuleSerializer(rule).data
            serialized_rules.append((serialized_rule, color))

        serialized.append({**ai_type, "rules": serialized_rules})

    return serialized


class RepositoryGroupSerializer(PublicIdMixin, serializers.ModelSerializer):
    repositories = serializers.SerializerMethodField()
    attested_num_lines = serializers.IntegerField(default=0)
    rules = RuleSerializer(many=True)
    usage_category = serializers.CharField(source="get_usage_category_display")

    class Meta:
        model = RepositoryGroup
        fields = [
            "public_id",
            "name",
            "repositories",
            "rules",
            "attested_num_lines",
            "not_evaluated_num_files",
            "usage_category",
            "percentage_ai_overall",
            "percentage_ai_pure",
            "percentage_ai_blended",
            "percentage_human",
            "code_num_lines",
            "roi_enabled",
        ]

    def get_repositories(self, obj):
        # has to be done like this to send context to the serializer
        repos = obj.repository_set
        return RepositorySerializer(repos, many=True, context=self.context).data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # has to be done here because it needs to get the serialized repository data
        if self.context.get("with_attestation_data", False):
            data["attested_num_lines"] = sum(
                repo["attested_num_lines"] for repo in data["repositories"]
            )
        return data


class AggregatedAuthorStatSerializer(serializers.Serializer):
    code_num_lines = serializers.IntegerField(
        allow_null=True, default=0,
    )
    code_ai_num_lines = serializers.IntegerField(
        allow_null=True, default=0,
    )
    code_ai_blended_num_lines = serializers.IntegerField(
        allow_null=True, default=0,
    )
    code_ai_pure_num_lines = serializers.IntegerField(
        allow_null=True, default=0,
    )
    code_not_ai_num_lines = serializers.IntegerField(
        allow_null=True, default=0,
    )
    percentage_ai_overall = serializers.SerializerMethodField()
    percentage_ai_blended = serializers.SerializerMethodField()
    percentage_ai_pure = serializers.SerializerMethodField()
    percentage_human = serializers.SerializerMethodField()

    def get_percentage_ai_overall(self, obj: dict):
        return self.calculate_percentage(
            obj.get("code_ai_num_lines", 0),
            obj.get("code_num_lines", 0),
        )

    def get_percentage_ai_blended(self, obj: dict):
        return self.calculate_percentage(
            obj.get("code_ai_blended_num_lines", 0),
            obj.get("code_num_lines", 0),
        )

    def get_percentage_ai_pure(self, obj: dict):
        return self.calculate_percentage(
            obj.get("code_ai_pure_num_lines", 0),
            obj.get("code_num_lines", 0),
        )

    def get_percentage_human(self, obj: dict):
        return self.calculate_percentage(
            obj.get("code_not_ai_num_lines", 0),
            obj.get("code_num_lines", 0),
        )

    @staticmethod
    def calculate_percentage(field_value: int, code_num_lines: int):
        if not code_num_lines:
            return Decimal(0)
        return (Decimal(field_value) * Decimal(100)) / Decimal(code_num_lines)


class AggregatedAuthorStatByDaySerializer(AggregatedAuthorStatSerializer):
    bucket = serializers.DateTimeField()


class AuthorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Author
        fields = [
            "public_id",
            "name",
            "email",
        ]


class AuthorGroupSerializer(serializers.ModelSerializer):
    developers = serializers.SerializerMethodField()
    developers_count = serializers.SerializerMethodField()
    rule_risk_list = serializers.SerializerMethodField()
    stats = AggregatedAuthorStatSerializer()

    class Meta:
        model = AuthorGroup
        fields = [
            "public_id",
            "name",
            "developers",
            "developers_count",
            "rule_risk_list",
            "stats",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Calculate deferred logic using serialized stats
        representation["rule_risk_list"] = self._get_rule_risk_list(
            instance, representation["stats"],
        )
        return representation

    # just send an empty list for now
    def get_developers(self, obj):
        return []

    def get_developers_count(self, obj):
        return obj.author_set.filter(linked_author__isnull=True).count()

    def get_rule_risk_list(self, obj):
        # As aggregated stats are needed for rule_risk_list and this is calculated in
        # AggregatedAuthorStatSerializer after this method runs we return None here
        # then calculate rule_risk_list in to_representation method.
        return []

    def _get_rule_risk_list(self, instance: AuthorGroup, stats: dict) -> list:
        org_rules = list(RuleService.get_organization_rules(instance.organization))
        all_rules = org_rules
        # only show group rules if stats are available
        if stats.get("code_num_lines"):
            all_rules += instance.rule_list()
        rules_list = list(
            zip(*RuleService.get_stats_rules_list(stats, all_rules))
        )
        rules, colors = rules_list if len(rules_list) == 2 else ([], [])
        rules_serialized = RuleSerializer(rules, many=True).data
        return list(zip(rules_serialized, colors))

