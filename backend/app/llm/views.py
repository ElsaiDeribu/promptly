import json
import logging
import os
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

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
from .serializers import CreateUploadURLSerializer
from .serializers import DocumentSerializer
from .serializers import RAGQuerySerializer
from .services.memory import delete_memory
from .services.memory import format_memories_for_prompt
from .services.memory import list_memories
from .services.memory import search_memories
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
):
    """Yield SSE events with streamed tokens from the RAG agent.

    Uses LangChain's ``astream_events`` (v2) so each LLM token is forwarded
    to the client as soon as it is produced.  The async generator is required
    by Django's ASGI handler for ``StreamingHttpResponse``.
    """
    try:
        agent = build_rag_agent(user_id=user_id, memory_context=memory_context)

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
        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
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
    """Poll the processing status of a document."""

    permission_classes = [IsAuthenticated]

    def get(self, request, document_id: int):
        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            DocumentSerializer(document).data,
            status=status.HTTP_200_OK,
        )
