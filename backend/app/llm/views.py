import json
import logging
import os
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

from django.db import transaction
from django.http import StreamingHttpResponse

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from langchain_core.messages import AIMessage
from langchain_core.messages import AIMessageChunk
from langchain_core.messages import HumanMessage

from .agents.rag_agent import build_rag_agent
from .models import Document
from .models import StudySectionProgress
from .serializers import CreateUploadURLSerializer
from .serializers import DocumentLayoutStatusSerializer
from .serializers import DocumentSerializer
from .serializers import EvalExamplesStatusSerializer
from .serializers import GenerateDocumentLayoutSerializer
from .serializers import GenerateEvalExamplesSerializer
from .serializers import GenerateSectionNotesSerializer
from .serializers import GenerateSectionQuestionsSerializer
from .serializers import GenerateStudyOutlineSerializer
from .serializers import RAGQuerySerializer
from .serializers import ReviseStudyOutlineSerializer
from .serializers import StudyOutlineStatusSerializer
from .serializers import StudySectionProgressSerializer
from .serializers import UpdateStudyProgressSerializer
from .services.memory import delete_memory
from .services.memory import format_memories_for_prompt
from .services.memory import list_memories
from .services.memory import search_memories
from .tasks import extract_document_layout_task
from .tasks import generate_eval_examples
from .tasks import generate_study_outline_task
from .tasks import process_document
from .utils.s3 import S3Wrapper

logger = logging.getLogger(__name__)


def _ollama_base_url() -> str:
    # When running via docker-compose, this resolves to the `ollama` service.
    return os.environ.get("OLLAMA_BASE_URL", "http://ollama:13000").rstrip("/")


def _ollama_request(
    path: str, payload: dict, timeout_s: float = 120.0,
) -> tuple[int, dict]:
    url = f"{_ollama_base_url()}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (local service)
            body = resp.read().decode("utf-8")
            return int(resp.status), json.loads(body) if body else {}
    except HTTPError as e:
        body = e.read().decode("utf-8") if hasattr(e, "read") else ""
        try:
            return int(e.code), json.loads(body) if body else {"error": str(e)}
        except json.JSONDecodeError:
            return int(e.code), {"error": body or str(e)}
    except (URLError, TimeoutError) as e:
        return 0, {"error": str(e)}


class OllamaChatView(APIView):
    """
    Proxy chat to Ollama.

    Request body (compatible-ish with OpenAI chat):
      - model: string (optional; defaults to env OLLAMA_MODEL or "llama3")
      - messages: [{role: "system"|"user"|"assistant", content: string}, ...] (required)
      - options: object (optional; forwarded to Ollama)
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        model = request.data.get("model") or os.environ.get("OLLAMA_MODEL") or "llama3"
        messages = request.data.get("messages")
        options = request.data.get("options") or {}

        if not isinstance(messages, list) or not messages:
            return Response(
                {"error": "`messages` must be a non-empty array"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        status_code, data = _ollama_request(
            "/api/chat",
            payload={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": options,
            },
        )

        if status_code == 0:
            return Response(
                {"error": "Failed to reach Ollama", "details": data},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if status_code >= 400:
            return Response(
                {"error": "Ollama error", "details": data},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        message = (data or {}).get("message") or {}
        return Response(
            {
                "model": (data or {}).get("model", model),
                "content": message.get("content", ""),
                "raw": data,
            },
            status=status.HTTP_200_OK,
        )


class OllamaModelsView(APIView):
    """
    List locally available models from Ollama (`/api/tags`).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        url = f"{_ollama_base_url()}/api/tags"
        req = Request(
            url=url, headers={"Content-Type": "application/json"}, method="GET",
        )
        try:
            with urlopen(req, timeout=10.0) as resp:  # noqa: S310 (local service)
                body = resp.read().decode("utf-8")
                data = json.loads(body) if body else {}
                return Response(data, status=status.HTTP_200_OK)
        except (HTTPError, URLError, TimeoutError) as e:
            return Response(
                {"error": "Failed to fetch Ollama models", "details": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )


def _sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(data)}\n\n"


def _to_langchain_messages(messages: list[dict]) -> list:
    lc_messages = []
    for message in messages:
        if message["role"] == "user":
            lc_messages.append(HumanMessage(content=message["content"]))
        else:
            lc_messages.append(AIMessage(content=message["content"]))
    return lc_messages


def _memory_search_query(messages: list[dict]) -> str:
    """Build a search query from the latest conversation turns."""
    recent = messages[-3:]
    return " ".join(message["content"] for message in recent if message.get("content"))


async def _rag_stream_generator(
    messages: list[dict],
    *,
    user_id: str,
    memory_context: str = "",
    document_id: int | None = None,
    section_context: str = "",
):
    """Yield SSE events with streamed tokens from the RAG agent.

    Uses LangChain's ``astream_events`` (v2) so each LLM token is forwarded
    to the client as soon as it is produced.  The async generator is required
    by Django's ASGI handler for ``StreamingHttpResponse``.
    """
    try:
        agent = build_rag_agent(
            user_id=user_id,
            memory_context=memory_context,
            document_id=document_id,
            section_context=section_context,
        )

        async for event in agent.astream_events(
            {"messages": _to_langchain_messages(messages)},
            version="v2",
            config={"run_name": "rag_agent_query"},
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    yield _sse_event({"token": chunk.content})
        yield _sse_event({"done": True})
    except Exception as e:
        logger.exception("RAG stream error")
        yield _sse_event({"error": str(e)})


class RAGQueryStreamView(APIView):
    """
    Stream a RAG answer as Server-Sent Events.

    DRF's ``APIView`` handles JWT authentication and permissions before the
    view method runs.  We then return Django's ``StreamingHttpResponse``
    which bypasses the DRF renderer pipeline and streams SSE events directly.

    Request body:
      - messages: [{role: "user"|"assistant", content: string}, ...] (preferred)
      - question: string (legacy single-turn fallback)

    Response: ``text/event-stream`` with JSON payloads:
      - ``{"token": "..."}`` – partial answer token
      - ``{"done": true}``   – stream finished
      - ``{"error": "..."}`` – an error occurred
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RAGQuerySerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        messages = serializer.validated_data["messages"]
        document_id = serializer.validated_data.get("document_id")
        section_context = serializer.validated_data.get("section_context") or ""
        user_id = str(request.user.id)
        memories = search_memories(
            user_id=user_id,
            query=_memory_search_query(messages),
            limit=10,
        )
        memory_context = format_memories_for_prompt(memories)

        response = StreamingHttpResponse(
            _rag_stream_generator(
                messages,
                user_id=user_id,
                memory_context=memory_context,
                document_id=document_id,
                section_context=section_context,
            ),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class UserMemoryListView(APIView):
    """List saved memories for the authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        memories = list_memories(user_id=str(request.user.id))
        return Response(
            [
                {
                    "memory_id": memory.memory_id,
                    "content": memory.content,
                    "context": memory.context,
                }
                for memory in memories
            ],
            status=status.HTTP_200_OK,
        )


class UserMemoryDetailView(APIView):
    """Delete a single saved memory."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, memory_id):
        deleted = delete_memory(
            user_id=str(request.user.id),
            memory_id=str(memory_id),
        )
        if not deleted:
            return Response(
                {"error": "Memory not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================
# Issues a presigned S3 URL and creates a Document.
# ============================================================
class CreateUploadURLView(APIView):
    """Endpoint to generate a presigned S3 upload URL and create a Document record.

    Returns a short-lived upload URL and S3 fields that the client can use for direct upload. 
    Creates a Document record in the database for the document.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateUploadURLSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = serializer.validated_data["filename"]
        content_type = serializer.validated_data["content_type"]

        document = Document.objects.create(
            user=request.user if request.user.is_authenticated else None,
            original_filename=filename,
            content_type=content_type,
        )
        document.s3_key = f"uploads/{document.upload_token}/{filename}"
        document.save(update_fields=["s3_key", "updated_at"])

        s3 = S3Wrapper()
        s3.ensure_bucket()
        upload_url = s3.generate_presigned_upload_url(
            object_name=document.s3_key,
            content_type=content_type,
        )

        if not upload_url:
            document.status = Document.Status.FAILED
            document.error_message = "Could not generate upload URL"
            document.save(update_fields=["status", "error_message", "updated_at"])
            return Response(
                {"error": "Failed to generate upload URL"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "document_id": str(document.id),
                "upload_url": upload_url,
                "method": "PUT",
                "content_type": content_type,
            },
            status=status.HTTP_201_CREATED,
        )


def _get_user_document(request, document_id: int) -> Document | None:
    try:
        return Document.objects.get(pk=document_id, user=request.user)
    except Document.DoesNotExist:
        return None


def _delete_document_and_assets(document: Document) -> None:
    """Delete stored files, vectors, and the document record."""
    s3 = S3Wrapper()
    for key in (document.s3_key, document.layout_s3_key, document.outline_s3_key):
        if key:
            s3.delete_file(key)

    try:
        from .utils.vector_db import VectorDBWrapper

        VectorDBWrapper().delete_by_document_id(document.id)
    except Exception:
        logger.exception("Failed to delete vectors for document %s", document.id)

    document.delete()


class CompleteUploadView(APIView):
    """
    Confirm upload and start async processing.

    Request body:
      - none (document_id is in the URL path)

    Returns:
      - document_id: string
      - status: string
      - message: string

    Kicks off background parsing and processing of the uploaded file.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id: int):
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        s3 = S3Wrapper()
        if not s3.object_exists(document.s3_key):
            return Response(
                {"error": "File not found in storage. Upload may not be complete."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document.status = Document.Status.UPLOADED
        document.error_message = ""
        document.save(update_fields=["status", "error_message", "updated_at"])

        # Async, non-blocking: parsing happens after this request returns.
        process_document.delay(document.id)

        return Response(
            {
                "document_id": str(document.id),
                "status": document.status,
                "message": "Upload complete. Processing started.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentDetailView(APIView):
    """Get or delete a document owned by the authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request, document_id: int):
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            DocumentSerializer(document).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, document_id: int):
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        _delete_document_and_assets(document)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentListView(APIView):
    """List documents uploaded by the authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        documents = Document.objects.filter(user=request.user).order_by("-created_at")
        return Response(
            DocumentSerializer(documents, many=True).data,
            status=status.HTTP_200_OK,
        )


class GenerateEvalExamplesView(APIView):
    """Generate golden eval examples for a processed document."""

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id: int):
        serializer = GenerateEvalExamplesSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            try:
                document = (
                    Document.objects.select_for_update().get(
                        pk=document_id,
                        user=request.user,
                    )
                )
            except Document.DoesNotExist:
                return Response(
                    {"error": "Document not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if document.status != Document.Status.PROCESSED:
                return Response(
                    {
                        "error": "Document must be processed before generating eval examples.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if document.eval_generation_status == "processing":
                return Response(
                    {
                        "document_id": str(document.id),
                        "eval_generation_status": document.eval_generation_status,
                        "message": "Eval example generation is already in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            previous_status = document.eval_generation_status
            document.eval_generation_status = "processing"
            document.save(update_fields=["eval_generation_status", "updated_at"])
            claimed_document_id = document.id

        sync_langsmith = serializer.validated_data["sync_langsmith"]
        try:
            generate_eval_examples.delay(
                claimed_document_id,
                sync_langsmith=sync_langsmith,
            )
        except Exception:
            logger.exception(
                "Failed to queue eval generation for document %s",
                claimed_document_id,
            )
            Document.objects.filter(pk=claimed_document_id).update(
                eval_generation_status=previous_status,
            )
            return Response(
                {"error": "Failed to queue eval example generation."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "document_id": str(claimed_document_id),
                "eval_generation_status": "processing",
                "message": "Generating eval examples.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class EvalExamplesStatusView(APIView):
    """Return golden eval example status for a document."""

    permission_classes = [IsAuthenticated]

    def get(self, request, document_id: int):
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        include_examples = request.query_params.get("include_examples") == "true"
        payload = {
            "document_id": document.id,
            "eval_generation_status": document.eval_generation_status,
            "eval_example_count": document.eval_examples.count(),
        }
        if include_examples:
            payload["examples"] = [
                {
                    "inputs": example.inputs,
                    "outputs": example.outputs,
                }
                for example in document.eval_examples.order_by("id")
            ]

        return Response(
            EvalExamplesStatusSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


def _load_layout_from_s3(document: Document) -> dict | None:
    if not document.layout_s3_key:
        return None

    s3 = S3Wrapper()
    raw = s3.get_file(document.layout_s3_key)
    if raw is None:
        return None

    return json.loads(raw.decode("utf-8"))


class DocumentLayoutView(APIView):
    """Return layout extraction status and layout payload when available."""

    permission_classes = [IsAuthenticated]

    def get(self, request, document_id: int):
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = {
            "document_id": document.id,
            "layout_generation_status": document.layout_generation_status,
            "layout_error_message": document.layout_error_message,
        }

        if document.layout_generation_status == "completed":
            layout = _load_layout_from_s3(document)
            if layout is not None:
                payload["layout"] = layout

        return Response(
            DocumentLayoutStatusSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


class GenerateDocumentLayoutView(APIView):
    """Generate or return cached Docling layout for a document."""

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id: int):
        serializer = GenerateDocumentLayoutSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        force = serializer.validated_data["force"]

        with transaction.atomic():
            try:
                document = (
                    Document.objects.select_for_update().get(
                        pk=document_id,
                        user=request.user,
                    )
                )
            except Document.DoesNotExist:
                return Response(
                    {"error": "Document not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if document.status == Document.Status.PENDING:
                return Response(
                    {"error": "Document upload must be complete before extracting layout."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            s3 = S3Wrapper()
            if not s3.object_exists(document.s3_key):
                return Response(
                    {"error": "File not found in storage."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if (
                document.layout_generation_status == "completed"
                and not force
            ):
                layout = _load_layout_from_s3(document)
                payload = {
                    "document_id": document.id,
                    "layout_generation_status": document.layout_generation_status,
                    "layout_error_message": document.layout_error_message,
                }
                if layout is not None:
                    payload["layout"] = layout
                return Response(
                    DocumentLayoutStatusSerializer(payload).data,
                    status=status.HTTP_200_OK,
                )

            if document.layout_generation_status == "processing":
                return Response(
                    {
                        "document_id": str(document.id),
                        "layout_generation_status": document.layout_generation_status,
                        "message": "Layout extraction is already in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            previous_status = document.layout_generation_status
            document.layout_generation_status = "processing"
            document.layout_error_message = ""
            document.save(
                update_fields=[
                    "layout_generation_status",
                    "layout_error_message",
                    "updated_at",
                ],
            )
            claimed_document_id = document.id

        try:
            extract_document_layout_task.delay(claimed_document_id)
        except Exception:
            logger.exception(
                "Failed to queue layout extraction for document %s",
                claimed_document_id,
            )
            Document.objects.filter(pk=claimed_document_id).update(
                layout_generation_status=previous_status,
            )
            return Response(
                {"error": "Failed to queue layout extraction."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "document_id": str(claimed_document_id),
                "layout_generation_status": "processing",
                "message": "Extracting document layout.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


def _load_outline_from_s3(document: Document) -> dict | None:
    if not document.outline_s3_key:
        return None

    s3 = S3Wrapper()
    raw = s3.get_file(document.outline_s3_key)
    if raw is None:
        return None

    return json.loads(raw.decode("utf-8"))


def _find_section_in_outline(outline: dict, section_id: str) -> dict | None:
    for section in outline.get("sections", []):
        if section.get("id") == section_id:
            return section
    return None


def _queue_study_outline(
    document: Document,
    *,
    revision_instruction: str = "",
) -> Response:
    previous_status = document.outline_generation_status
    document.outline_generation_status = "processing"
    document.outline_error_message = ""
    document.save(
        update_fields=[
            "outline_generation_status",
            "outline_error_message",
            "updated_at",
        ],
    )
    claimed_document_id = document.id

    try:
        generate_study_outline_task.delay(
            claimed_document_id,
            revision_instruction=revision_instruction,
        )
    except Exception:
        logger.exception(
            "Failed to queue study outline for document %s",
            claimed_document_id,
        )
        Document.objects.filter(pk=claimed_document_id).update(
            outline_generation_status=previous_status,
        )
        return Response(
            {"error": "Failed to queue study outline generation."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            "document_id": str(claimed_document_id),
            "outline_generation_status": "processing",
            "message": "Generating study outline.",
        },
        status=status.HTTP_202_ACCEPTED,
    )


class StudyOutlineView(APIView):
    """Return study outline status and payload when available."""

    permission_classes = [IsAuthenticated]

    def get(self, request, document_id: int):
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = {
            "document_id": document.id,
            "outline_generation_status": document.outline_generation_status,
            "outline_error_message": document.outline_error_message,
        }

        if document.outline_generation_status == "completed":
            outline = _load_outline_from_s3(document)
            if outline is not None:
                payload["outline"] = outline

        return Response(
            StudyOutlineStatusSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


class GenerateStudyOutlineView(APIView):
    """Generate or return cached study outline for a document."""

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id: int):
        serializer = GenerateStudyOutlineSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        force = serializer.validated_data["force"]

        with transaction.atomic():
            try:
                document = (
                    Document.objects.select_for_update().get(
                        pk=document_id,
                        user=request.user,
                    )
                )
            except Document.DoesNotExist:
                return Response(
                    {"error": "Document not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if document.layout_generation_status != "completed":
                return Response(
                    {"error": "Document layout must be extracted before generating study outline."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if (
                document.outline_generation_status == "completed"
                and not force
            ):
                outline = _load_outline_from_s3(document)
                payload = {
                    "document_id": document.id,
                    "outline_generation_status": document.outline_generation_status,
                    "outline_error_message": document.outline_error_message,
                }
                if outline is not None:
                    payload["outline"] = outline
                return Response(
                    StudyOutlineStatusSerializer(payload).data,
                    status=status.HTTP_200_OK,
                )

            if document.outline_generation_status == "processing":
                return Response(
                    {
                        "document_id": str(document.id),
                        "outline_generation_status": document.outline_generation_status,
                        "message": "Study outline generation is already in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            return _queue_study_outline(document)


class ReviseStudyOutlineView(APIView):
    """Revise an existing study outline based on user feedback."""

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id: int):
        serializer = ReviseStudyOutlineSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instruction = serializer.validated_data["instruction"]

        with transaction.atomic():
            try:
                document = (
                    Document.objects.select_for_update().get(
                        pk=document_id,
                        user=request.user,
                    )
                )
            except Document.DoesNotExist:
                return Response(
                    {"error": "Document not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if document.outline_generation_status != "completed":
                return Response(
                    {"error": "Study outline must exist before revising."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if document.outline_generation_status == "processing":
                return Response(
                    {
                        "document_id": str(document.id),
                        "outline_generation_status": "processing",
                        "message": "Study outline revision is already in progress.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            return _queue_study_outline(
                document,
                revision_instruction=instruction,
            )


class StudyProgressView(APIView):
    """List or update per-section study progress."""

    permission_classes = [IsAuthenticated]

    def get(self, request, document_id: int):
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        progress = StudySectionProgress.objects.filter(
            user=request.user,
            document=document,
        )
        return Response(
            StudySectionProgressSerializer(progress, many=True).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, document_id: int):
        serializer = UpdateStudyProgressSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from django.utils import timezone

        section_id = serializer.validated_data["section_id"]
        defaults: dict = {}
        if "completed" in serializer.validated_data:
            completed = serializer.validated_data["completed"]
            defaults["completed"] = completed
            defaults["completed_at"] = timezone.now() if completed else None
        if "notes" in serializer.validated_data:
            defaults["notes"] = serializer.validated_data["notes"]

        progress, _ = StudySectionProgress.objects.update_or_create(
            user=request.user,
            document=document,
            section_id=section_id,
            defaults=defaults,
        )
        return Response(
            StudySectionProgressSerializer(progress).data,
            status=status.HTTP_200_OK,
        )


class SectionNotesView(APIView):
    """Generate or return cached study notes for a section."""

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id: int, section_id: str):
        serializer = GenerateSectionNotesSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        force = serializer.validated_data["force"]
        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        outline = _load_outline_from_s3(document)
        if outline is None:
            return Response(
                {"error": "Study outline not available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        section = _find_section_in_outline(outline, section_id)
        if section is None:
            return Response(
                {"error": "Section not found in outline."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .services.study_outline.outline_generator import generate_section_notes
        from .services.study_outline.outline_generator import section_study_scope

        scoped_section = section_study_scope(section, outline)

        progress = StudySectionProgress.objects.filter(
            user=request.user,
            document=document,
            section_id=section_id,
        ).first()

        if progress and progress.notes and not force:
            return Response(
                {"section_id": section_id, "notes": progress.notes},
                status=status.HTTP_200_OK,
            )

        layout = _load_layout_from_s3(document)
        if layout is None:
            return Response(
                {"error": "Document layout not available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = generate_section_notes(
            layout,
            scoped_section,
            filename=document.original_filename,
        )

        StudySectionProgress.objects.update_or_create(
            user=request.user,
            document=document,
            section_id=section_id,
            defaults={"notes": notes},
        )

        return Response(
            {"section_id": section_id, "notes": notes},
            status=status.HTTP_200_OK,
        )


class SectionQuestionsView(APIView):
    """Generate practice questions for a study section."""

    permission_classes = [IsAuthenticated]

    def post(self, request, document_id: int, section_id: str):
        serializer = GenerateSectionQuestionsSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document = _get_user_document(request, document_id)
        if document is None:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        outline = _load_outline_from_s3(document)
        if outline is None:
            return Response(
                {"error": "Study outline not available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        section = _find_section_in_outline(outline, section_id)
        if section is None:
            return Response(
                {"error": "Section not found in outline."},
                status=status.HTTP_404_NOT_FOUND,
            )

        layout = _load_layout_from_s3(document)
        if layout is None:
            return Response(
                {"error": "Document layout not available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .services.study_outline.outline_generator import generate_section_questions
        from .services.study_outline.outline_generator import section_study_scope

        scoped_section = section_study_scope(section, outline)

        questions = generate_section_questions(
            layout,
            scoped_section,
            filename=document.original_filename,
            count=serializer.validated_data["count"],
        )

        return Response(
            {"section_id": section_id, "questions": questions},
            status=status.HTTP_200_OK,
        )
