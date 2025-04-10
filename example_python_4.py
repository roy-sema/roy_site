
ifrom datetime import date, datetime

from django.db.models import QuerySet
from django.utils import timezone

from compass.codebasereports.widgets.sema_score_widget import SemaScoreWidget
from mvp.models import AITypeChoices, Organization, Repository, RepositoryCommit
from mvp.services import (
    AICompositionService,
    ConnectedIntegrationsService,
    ContextualizationService,
    ContextualizationDayInterval,
)


class AggregatedMessageService:

    ATTENTION_LEVEL_CEO = "attention_level_ceo"
    ATTENTION_LEVEL_CEO_OR_CPO = "attention_level_ceo_or_cpo"
    ATTENTION_LEVEL_DIRECTOR_OR_MANAGER = "attention_level_director_or_manager"
    ATTENTION_LEVEL_TEAM_LEAD = "attention_level_team_lead"

    ATTENTION_LEVELS_MAP = {
        10: ATTENTION_LEVEL_CEO,
        9: ATTENTION_LEVEL_CEO_OR_CPO,
        8: ATTENTION_LEVEL_DIRECTOR_OR_MANAGER,
        7: ATTENTION_LEVEL_TEAM_LEAD,
    }

    @classmethod
    def get_for_day_interval(
        cls,
        organization: Organization,
        day_interval: ContextualizationDayInterval,
    ):
        """
        This collects data from various services across the system to
        provide data for the daily and weekly message emails and views.

        NOTE: If the `file_timestamp_is_today` is False, it means that
        the contextualization script did not run for whatever reason today.
        Using this flag, logic should decide what to do in this case.
        """
        end = timezone.now()
        start = end - timezone.timedelta(days=day_interval.value)

        repositories = organization.repository_set.all()

        anomaly_insights_and_risks, file_timestamp = cls.get_anomaly_insights_and_risks(
            organization, repositories, day_interval
        )
        last_updated = datetime.fromtimestamp(file_timestamp, tz=timezone.utc)
        return {
            "last_updated": last_updated,
            "updated_today": end <= last_updated,
            "codebase_health": cls.get_codebase_health(
                organization, start.date(), end.date()
            ),
            "percentage_ai": cls.get_percentage_ai(organization, start, end),
            "anomaly_insights_and_risks": anomaly_insights_and_risks,
            "data_sets_used": cls.get_data_sets_used(organization),
        }

    @staticmethod
    def get_organization_commits(
        organization: Organization,
        start: datetime,
        end: datetime,
    ):
        return RepositoryCommit.objects.filter(
            repository__organization=organization,
            created_by__range=(start, end),
        )

    @staticmethod
    def get_codebase_health(organization: Organization, start: date, end: date):
        score_widget = SemaScoreWidget(organization)
        chart_score, _, _ = score_widget.get_charts(start, end)
        return score_widget.get_score(chart_score)

    @staticmethod
    def get_percentage_ai(organization: Organization, start: datetime, end: datetime):
        service = AICompositionService(organization)
        cumulative_charts, daily_charts = service.get_charts(start, end)
        ai_composition = service.get_composition(cumulative_charts)

        return next(
            (
                item
                for item in ai_composition
                if item["label"] == AITypeChoices.OVERALL.label
            ),
            None,
        )

    @classmethod
    def get_anomaly_insights_and_risks(
        cls,
        organization: Organization,
        repositories: QuerySet[Repository],
        day_interval: ContextualizationDayInterval,
    ):
        data, file_timestamp = ContextualizationService.load_output_data(
            organization,
            ContextualizationService.OUTPUT_FILENAME_COMBINED_ANOMALY_INSIGHTS,
            day_interval=day_interval,
        )
        return cls.format_anomaly_insights_and_risks(data, repositories), file_timestamp

    @classmethod
    def format_anomaly_insights_and_risks(
        cls, data: dict, repositories: QuerySet[Repository]
    ):
        formatted_anomaly_insights_and_risks = {
            cls.ATTENTION_LEVEL_CEO: [],
            cls.ATTENTION_LEVEL_CEO_OR_CPO: [],
            cls.ATTENTION_LEVEL_DIRECTOR_OR_MANAGER: [],
            cls.ATTENTION_LEVEL_TEAM_LEAD: [],
        }

        repository_public_id_map = {repo.public_id(): repo for repo in repositories}

        for anomaly_insight in data.get("anomaly_insights", []):
            attention_level = AggregatedMessageService.ATTENTION_LEVELS_MAP.get(
                anomaly_insight["significance_score"]
            )
            if not attention_level:
                continue

            formatted_anomaly_insights_and_risks[attention_level].append(
                {
                    "type": "anomaly",
                    **cls.replace_insight_repo_public_id_with_full_name(
                        anomaly_insight, repository_public_id_map
                    ),
                }
            )

        for risk_insight in data.get("risk_insights", []):
            attention_level = AggregatedMessageService.ATTENTION_LEVELS_MAP.get(
                risk_insight["significance_score"]
            )
            if not attention_level:
                continue

            formatted_anomaly_insights_and_risks[attention_level].append(
                {
                    "type": "risk",
                    **cls.replace_insight_repo_public_id_with_full_name(
                        risk_insight, repository_public_id_map
                    ),
                }
            )

        return formatted_anomaly_insights_and_risks

    @staticmethod
    def replace_insight_repo_public_id_with_full_name(
        insight: dict, repository_public_id_map: dict
    ):
        repository_public_id = insight["repo"]
        repository = repository_public_id_map[insight["repo"]]
        return {
            key: (
                value.replace(repository_public_id, repository.full_name())
                if isinstance(value, str) and key != "repo"
                else value
            )
            for key, value in insight.items()
        }

    @staticmethod
    def get_data_sets_used(organization: Organization):
        return ConnectedIntegrationsService.get_connected_integrations_names(
            organization, use_display_names=True
        )

