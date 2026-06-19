from django.urls import path

from .views import OllamaChatView
from .views import OllamaModelsView
from .views import ProcessPDFView
from .views import RAGQueryStreamView

urlpatterns = [
    path("chat", OllamaChatView.as_view(), name="ollama-chat"),
    path("models", OllamaModelsView.as_view(), name="ollama-models"),
    path("rag/process", ProcessPDFView.as_view(), name="rag-process-pdf"),
    path("rag/query/stream", RAGQueryStreamView.as_view(), name="rag-query-stream"),
]

