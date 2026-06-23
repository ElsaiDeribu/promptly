from uuid import uuid4

from django.conf import settings
from django.db import models


class Document(models.Model):
    """Tracks the lifecycle of a PDF from upload to processing.

    Holds metadata and an S3 pointer for files processed through the
    multimodal RAG pipeline via Celery.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending upload"
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    original_filename = models.CharField(max_length=512)
    content_type = models.CharField(max_length=128, default="application/pdf")
    # Token used to build a collision-free S3 object key.
    upload_token = models.UUIDField(default=uuid4, editable=False, unique=True)
    s3_key = models.CharField(max_length=1024)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.status})"
