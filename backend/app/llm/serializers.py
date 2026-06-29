from rest_framework import serializers

from .models import Document


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()


class RAGQuerySerializer(serializers.Serializer):
    """
    Schema for RAG Query
    """

    question = serializers.CharField(
        required=False,
        help_text="Single-turn question (legacy; use messages for multi-turn)",
    )
    messages = ChatMessageSerializer(
        many=True,
        required=False,
        help_text="Sliding window of conversation messages",
    )

    def validate(self, attrs):
        messages = attrs.get("messages")
        question = attrs.get("question")
        if messages:
            return attrs
        if question:
            attrs["messages"] = [{"role": "user", "content": question}]
            return attrs
        raise serializers.ValidationError(
            "Either `messages` or `question` is required.",
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

    eval_example_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "original_filename",
            "content_type",
            "status",
            "error_message",
            "eval_generation_status",
            "eval_example_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_eval_example_count(self, obj: Document) -> int:
        return obj.eval_examples.count()


class GenerateEvalExamplesSerializer(serializers.Serializer):
    sync_langsmith = serializers.BooleanField(required=False, default=False)


class EvalExamplesStatusSerializer(serializers.Serializer):
    document_id = serializers.IntegerField()
    eval_generation_status = serializers.CharField()
    eval_example_count = serializers.IntegerField()
    examples = serializers.ListField(child=serializers.DictField(), required=False)
