import json
import logging

from cto_tool import settings
from django.core.mail import send_mail
from django.core.mail import send_mass_mail
from django.template.loader import render_to_string
from django.urls import reverse
from mvp.utils import traceback_on_debug
from sentry_sdk import capture_exception, capture_message, push_scope

logger = logging.getLogger(__name__)


class EmailService:
    # TODO refactor this to reduce code duplication

    @staticmethod
    def send_email(
        subject,
        message,
        from_email,
        recipient_list,
        auth_user=None,
        auth_password=None,
        connection=None,
        html_message=None,
    ):
        if not recipient_list:
            with push_scope() as scope:
                scope.set_extra("subject", subject)
                scope.set_extra("message", message)
                scope.set_extra("from_email", from_email)
            error_message = "failed to send emails. Empty recipient list"
            capture_message(error_message)
            logger.error(error_message)

        try:
            send_mail(
                subject,
                message,
                from_email,
                recipient_list,
                auth_user=auth_user,
                auth_password=auth_password,
                connection=connection,
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            with push_scope() as scope:
                scope.set_extra("subject", subject)
                scope.set_extra("message", message)
                scope.set_extra("from_email", from_email)
                scope.set_extra("recipient_list", json.dumps(recipient_list))
            traceback_on_debug()
            capture_exception(e)
            logger.error(f"failed to send emails to {recipient_list}")
            return False

        return True
