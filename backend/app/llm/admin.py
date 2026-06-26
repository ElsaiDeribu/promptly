from django.contrib import admin

from .models import Document
from .models import UserMemory


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "original_filename", "status", "user", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["original_filename", "s3_key", "upload_token"]
    readonly_fields = ["upload_token", "created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(UserMemory)
class UserMemoryAdmin(admin.ModelAdmin):
    list_display = ["memory_id", "user", "content_preview", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["content", "context", "memory_id"]
    readonly_fields = ["memory_id", "created_at", "updated_at"]
    ordering = ["-updated_at"]

    @admin.display(description="Content")
    def content_preview(self, obj: UserMemory) -> str:
        return obj.content[:80]
