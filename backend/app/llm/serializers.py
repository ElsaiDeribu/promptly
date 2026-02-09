from rest_framework import serializers


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
