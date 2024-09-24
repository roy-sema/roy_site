from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from .models import GenAIFeedback


@admin.register(GenAIFeedback)
class GenAIFeedbackAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "user",
        "file_path",
        "code_line_start",
        "code_line_end",
        "status",
        "vote",
        "get_comment_truncated_display",
    )
    list_filter = ("vote", "status")
    search_fields = ("user__email", "file")

    def get_comment_truncated_display(self, obj):
        return obj.get_comment_truncated()

    get_comment_truncated_display.short_description = "Comment"
