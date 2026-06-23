from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "original_filename", "status", "user", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["original_filename", "s3_key", "upload_token"]
    readonly_fields = ["upload_token", "created_at", "updated_at"]
    ordering = ["-created_at"]
