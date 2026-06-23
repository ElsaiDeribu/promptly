from rest_framework import serializers

from .models import Document


class ProcessPDFSerializer(serializers.Serializer):
    """
    Schema for PDF Processing
    """

    file = serializers.FileField(
        help_text="PDF file to process for multimodal RAG",
    )


class RAGQuerySerializer(serializers.Serializer):
    """
    Schema for RAG Query
    """

    question = serializers.CharField(
        help_text="Question to ask about the processed documents",
    )


class CreateUploadURLSerializer(serializers.Serializer):
    """Request schema for STEP 1 - request a pre-signed upload URL."""

    filename = serializers.CharField(
        max_length=512,
        help_text="Original name of the file to be uploaded",
    )
    content_type = serializers.CharField(
        max_length=128,
        required=False,
        default="application/pdf",
        help_text="MIME type of the file (must match the PUT request header)",
    )

    def validate_filename(self, value: str) -> str:
        if not value.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are supported.")
        return value


class DocumentSerializer(serializers.ModelSerializer):
    """Read schema for a document's processing state."""

    class Meta:
        model = Document
        fields = [
            "id",
            "original_filename",
            "content_type",
            "status",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
