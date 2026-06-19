import json
import logging
import os
import tempfile
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

from django.http import StreamingHttpResponse

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from langchain_core.messages import AIMessageChunk
from langchain_core.messages import HumanMessage

from .agents.rag_agent import rag_agent
from .serializers import ProcessPDFSerializer
from .serializers import RAGQuerySerializer
from .services.multimodal_rag.rag_pipeline import create_processing_graph
from .services.multimodal_rag.rag_pipeline import create_processing_state

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


class ProcessPDFView(APIView):
    """
    Process a PDF file for multimodal RAG.

    This endpoint accepts a PDF file, processes it to extract text, tables, and images,
    generates summaries, and stores them in the vector database for later retrieval.

    Request:
      - file: PDF file (multipart/form-data)

    Response:
      - success: boolean
      - message: string
      - filename: string (name of processed file)
    """

    def post(self, request):
        serializer = ProcessPDFSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_file = serializer.validated_data["file"]

        # Save uploaded file to a temporary location
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".pdf", prefix="rag_",
            ) as tmp_file:
                for chunk in uploaded_file.chunks():
                    tmp_file.write(chunk)
                temp_path = tmp_file.name

            # Process the PDF using the RAG pipeline
            processing_graph = create_processing_graph()
            initial_state = create_processing_state(temp_path)
            processing_graph.invoke(initial_state)

            # Clean up temporary file
            os.unlink(temp_path)

            return Response(
                {
                    "success": True,
                    "message": "PDF processed successfully",
                    "filename": uploaded_file.name,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            # Clean up temporary file if it exists
            if "temp_path" in locals():
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

            return Response(
                {"error": "Failed to process PDF", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def _sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(data)}\n\n"


async def _rag_stream_generator(question: str):
    """Yield SSE events with streamed tokens from the RAG agent.

    Uses LangChain's ``astream_events`` (v2) so each LLM token is forwarded
    to the client as soon as it is produced.  The async generator is required
    by Django's ASGI handler for ``StreamingHttpResponse``.
    """
    try:
        async for event in rag_agent.astream_events(
            {"messages": [HumanMessage(content=question)]},
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
      - question: string (required)

    Response: ``text/event-stream`` with JSON payloads:
      - ``{"token": "..."}`` – partial answer token
      - ``{"done": true}``   – stream finished
      - ``{"error": "..."}`` – an error occurred
    """

    def post(self, request):
        serializer = RAGQuerySerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = serializer.validated_data["question"]

        response = StreamingHttpResponse(
            _rag_stream_generator(question),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
