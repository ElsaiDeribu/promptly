import json
import os
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ProcessPDFSerializer, RAGQuerySerializer
from .services.multimodal_rag.rag_pipeline import (
    create_chat_graph,
    create_chat_state,
    create_processing_graph,
    create_processing_state,
)


def _ollama_base_url() -> str:
    # When running via docker-compose, this resolves to the `ollama` service.
    return os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")


def _ollama_request(
    path: str, payload: dict, timeout_s: float = 120.0
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
            url=url, headers={"Content-Type": "application/json"}, method="GET"
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
                delete=False, suffix=".pdf", prefix="rag_"
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


class RAGQueryView(APIView):
    """
    Query the multimodal RAG system.

    This endpoint accepts a question and retrieves relevant context from processed
    documents (text, tables, images) to generate an answer.

    Request body:
      - question: string (required)

    Response:
      - question: string (the original question)
      - answer: string (generated answer)
      - context: object with texts and image URLs
    """

    def post(self, request):
        serializer = RAGQuerySerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = serializer.validated_data["question"]

        try:
            chat_graph = create_chat_graph()
            chat_state = create_chat_state(question)
            result = chat_graph.invoke(chat_state)

            # Extract response
            if isinstance(result["current_response"], str):
                answer = result["current_response"]
                context = result.get("context", {})
            else:
                answer = result["current_response"].get("response", "")
                context = result["current_response"].get("context", {})

            return Response(
                {
                    "question": question,
                    "answer": answer,
                    "context": context,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": "Failed to process query", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
