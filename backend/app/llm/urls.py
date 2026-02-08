from django.urls import path

from .views import OllamaChatView, OllamaModelsView, ProcessPDFView, RAGQueryView

urlpatterns = [
    path("chat", OllamaChatView.as_view(), name="ollama-chat"),
    path("models", OllamaModelsView.as_view(), name="ollama-models"),
    path("rag/process", ProcessPDFView.as_view(), name="rag-process-pdf"),
    path("rag/query", RAGQueryView.as_view(), name="rag-query"),
]

