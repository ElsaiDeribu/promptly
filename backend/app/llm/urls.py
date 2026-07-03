from django.urls import path

from .views import CompleteUploadView
from .views import CreateUploadURLView
from .views import DocumentDetailView
from .views import DocumentLayoutView
from .views import DocumentListView
from .views import EvalExamplesStatusView
from .views import GenerateDocumentLayoutView
from .views import GenerateEvalExamplesView
from .views import GenerateStudyOutlineView
from .views import OllamaChatView
from .views import OllamaModelsView
from .views import RAGQueryStreamView
from .views import ReviseStudyOutlineView
from .views import SectionNotesView
from .views import SectionQuestionsView
from .views import StudyOutlineView
from .views import StudyProgressView
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
        "documents",
        DocumentListView.as_view(),
        name="documents-list",
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
    path(
        "documents/<int:document_id>/generate-eval-examples",
        GenerateEvalExamplesView.as_view(),
        name="documents-generate-eval-examples",
    ),
    path(
        "documents/<int:document_id>/eval-examples",
        EvalExamplesStatusView.as_view(),
        name="documents-eval-examples",
    ),
    path(
        "documents/<int:document_id>/layout",
        DocumentLayoutView.as_view(),
        name="documents-layout",
    ),
    path(
        "documents/<int:document_id>/layout/generate",
        GenerateDocumentLayoutView.as_view(),
        name="documents-layout-generate",
    ),
    path(
        "documents/<int:document_id>/study-outline",
        StudyOutlineView.as_view(),
        name="documents-study-outline",
    ),
    path(
        "documents/<int:document_id>/study-outline/generate",
        GenerateStudyOutlineView.as_view(),
        name="documents-study-outline-generate",
    ),
    path(
        "documents/<int:document_id>/study-outline/revise",
        ReviseStudyOutlineView.as_view(),
        name="documents-study-outline-revise",
    ),
    path(
        "documents/<int:document_id>/study-progress",
        StudyProgressView.as_view(),
        name="documents-study-progress",
    ),
    path(
        "documents/<int:document_id>/study-sections/<str:section_id>/notes",
        SectionNotesView.as_view(),
        name="documents-study-section-notes",
    ),
    path(
        "documents/<int:document_id>/study-sections/<str:section_id>/questions",
        SectionQuestionsView.as_view(),
        name="documents-study-section-questions",
    ),
]
