from django.conf import settings
from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from mvp.models import Organization
from mvp.services import EmailService
from mvp.services.aggregated_message_service import AggregatedMessageService
from mvp.services.contextualization_service import ContextualizationDayInterval


class Command(BaseCommand):
    help = "Generate and send the Daily Message email"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", type=str, help="Filename to save the email content."
        )
        parser.add_argument(
            "--orgid",
            type=int,
            help="Narrow execution just to given organization ID.",
        )

    def handle(self, *args, **options):
        try:
            organization_id = options.get("orgid", 0)
            if organization_id:
                organizations = Organization.objects.filter(id=organization_id)
                if not organizations:
                    raise CommandError(
                        f'Organization with ID "{organization_id}" does not exist.'
                    )
            else:
                organizations = Organization.objects.all()

            emails_sent_to_orgs = []
            for organization in organizations:
                data = self.get_daily_message_data(organization)

                content = render_to_string(
                    "mvp/emails/daily_message.txt", {"message": data}
                )

                if options.get("output"):
                    with open(f"{options['output']}.txt", "w") as f:
                        f.write(content)

                    self.stdout.write(
                        self.style.SUCCESS(f"Email saved to {options['output']}")
                    )

                emails_sent_to_orgs.append(organization.name)

                self.send_email(
                    subject=f"SIP-Daily Message - {organization.name}",
                    message=content,
                )

            self.stdout.write(
                self.style.SUCCESS(
                    "Daily message email sent to "
                    f"organizations: {', '.join(emails_sent_to_orgs) or 'None'}"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            raise

    def get_daily_message_data(self, organization):
        """
        Get data for the daily message.
        In a real implementation, this would likely fetch from databases or APIs.
        """
        data = AggregatedMessageService.get_for_day_interval(
            organization, ContextualizationDayInterval.ONE_DAY
        )

        risk_map = {
            x["significance_score"]: x
            for x in data["anomaly_insights_and_risks"]["risk_insights"]
        }

        anomaly_map = {
            x["significance_score"]: x
            for x in data["anomaly_insights_and_risks"]["anomaly_insights"]
        }

        insights = []
        for score in (10, 9, 8, 7):
            anomaly = anomaly_map.get(score)
            risk = risk_map.get(score)
            items = []

            if anomaly:
                items.append(anomaly)

            if risk:
                items.append(risk)

            if not items:
                continue

            insights.append(items)

        return {
            "last_updated": timezone.now(),
            "organization": organization,
            "insights": insights,
        }

    def send_email(self, subject, message):
        """Send the daily message email"""
        EmailService.send_email(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DAILY_MESSAGE_RECIPIENT],
        )
