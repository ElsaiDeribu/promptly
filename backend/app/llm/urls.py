from django.urls import path

from .views import CompleteUploadView
from .views import CreateUploadURLView
from .views import DocumentDetailView
from .views import OllamaChatView
from .views import OllamaModelsView
from .views import RAGQueryStreamView
from .views import UserMemoryDetailView
from .views import UserMemoryListView

urlpatterns = [
    path("chat", OllamaChatView.as_view(), name="ollama-chat"),
    path("models", OllamaModelsView.as_view(), name="ollama-models"),
    path("rag/query/stream", RAGQueryStreamView.as_view(), name="rag-query-stream"),
    path("memories", UserMemoryListView.as_view(), name="user-memories-list"),
    path(
        "memories/<uuid:memory_id>",
        UserMemoryDetailView.as_view(),
        name="user-memories-detail",
    ),
    # Direct-to-S3 upload flow
    path(
        "documents/create-upload-url",
        CreateUploadURLView.as_view(),
        name="documents-create-upload-url",
    ),
    path(
        "documents/<int:document_id>/complete-upload",
        CompleteUploadView.as_view(),
        name="documents-complete-upload",
    ),
    path(
        "documents/<int:document_id>",
        DocumentDetailView.as_view(),
        name="documents-detail",
    ),
]
