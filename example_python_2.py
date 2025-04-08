from datetime import date, datetime

from django.utils import timezone

from compass.codebasereports.widgets.sema_score_widget import SemaScoreWidget
from compass.dashboard.views import DashboardView
from mvp.models import AITypeChoices, Organization
from mvp.services import (
    AICompositionService,
    ConnectedIntegrationsService,
    ContextualizationService,
    ContextualizationDayInterval,
)


class AggregatedMessageService:

    @classmethod
    def get_for_day_interval(
        cls, organization: Organization, day_interval: ContextualizationDayInterval,
    ):
        end = timezone.now()
        start = end - timezone.timedelta(days=day_interval.value)

        return {
            "codebase_health": cls.get_codebase_health(
                organization, start.date(), end.date()
            ),
            "percentage_ai": cls.get_percentage_ai(organization, start, end),
            "initiatives": cls.get_initiatives(organization, day_interval),
            "summary_insights": cls.get_summary_insights(
                organization, start, end, day_interval
            ),
            "data_sets_used": cls.get_data_sets_used(organization),
        }

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

    @staticmethod
    def get_initiatives(
        organization: Organization, day_interval: ContextualizationDayInterval
    ):
        data, _ = ContextualizationService.load_output_data(
            organization,
            ContextualizationService.OUTPUT_FILENAME_ROADMAP,
            day_interval=day_interval,
        )
        return data.get("initiatives", [])

    @staticmethod
    def get_summary_insights(
        organization: Organization,
        start: datetime,
        end: datetime,
        day_interval: ContextualizationDayInterval
    ):
        # TODO: I'm not sure we're going to use as -
        #  'We don't have Summary Insights talking about x% changes'.
        #  If replaced by another pipeline remove this method.

        # TODO - super scrappy at the moment. If it is decided summary insights are to be
        #  used in this way we should refactor DashboardView to be a service.

        # Doing this as DashboardView expects start
        # and end dates to not be timezone aware.
        start_date = start.replace(tzinfo=None)
        end_date = end.replace(tzinfo=None)

        repositories = organization.repository_set.all()
        count_data = DashboardView.get_count_data(organization, start_date, end_date)
        data, _ = ContextualizationService.load_output_data(
            organization,
            ContextualizationService.OUTPUT_FILENAME_JUSTIFICATION,
            day_interval=day_interval,
        )
        if not data:
            return None

        normalized_data = DashboardView.normalize_justification(data, count_data)
        return DashboardView.enhance_justification(normalized_data, repositories)

    @staticmethod
    def get_data_sets_used(organization: Organization):
        return ConnectedIntegrationsService.get_connected_integrations_names(
            organization, use_display_names=True
        )

