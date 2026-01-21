import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


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
