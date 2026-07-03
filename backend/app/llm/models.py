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
    eval_generation_status = models.CharField(
        max_length=16,
        choices=[
            ("none", "None"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="none",
        db_index=True,
    )
    layout_generation_status = models.CharField(
        max_length=16,
        choices=[
            ("none", "None"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="none",
        db_index=True,
    )
    layout_s3_key = models.CharField(max_length=1024, blank=True, default="")
    layout_error_message = models.TextField(blank=True, default="")
    outline_generation_status = models.CharField(
        max_length=16,
        choices=[
            ("none", "None"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="none",
        db_index=True,
    )
    outline_s3_key = models.CharField(max_length=1024, blank=True, default="")
    outline_error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.status})"


class UserMemory(models.Model):
    """Long-term memory scoped to a user, persisted across chat sessions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memories",
    )
    memory_id = models.UUIDField(default=uuid4, editable=False, unique=True)
    content = models.TextField()
    context = models.TextField(blank=True, default="")
    embedding = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.content[:60]}"


class EvalExample(models.Model):
    """Golden eval example generated from an ingested document."""

    class Source(models.TextChoices):
        GENERATED = "generated", "Generated"

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="eval_examples",
    )
    inputs = models.JSONField()
    outputs = models.JSONField(default=dict)
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.GENERATED,
    )
    # TODO: Add a bidirectional sync to the LangSmith.
    langsmith_example_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        question = (self.inputs or {}).get("question", "")
        return f"EvalExample({self.document_id}): {question[:60]}"


class StudySectionProgress(models.Model):
    """Per-user progress and cached notes for a study outline section."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_section_progress",
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="study_section_progress",
    )
    section_id = models.CharField(max_length=128)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["section_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document", "section_id"],
                name="unique_study_section_progress",
            ),
        ]

    def __str__(self) -> str:
        status = "done" if self.completed else "pending"
        return f"StudySectionProgress({self.document_id}/{self.section_id}): {status}"
