"""Per-user long-term memory backed by Django ORM with semantic search."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from uuid import UUID
from uuid import uuid4

from django.contrib.auth import get_user_model
from langchain_openai import OpenAIEmbeddings

from ..models import UserMemory

logger = logging.getLogger(__name__)
User = get_user_model()

_embeddings: OpenAIEmbeddings | None = None


def _get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings()
    return _embeddings


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    content: str
    context: str
    score: float | None = None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_text(text: str) -> list[float]:
    return _get_embeddings().embed_query(text)


def upsert_memory(
    *,
    user_id: str,
    content: str,
    context: str = "",
    memory_id: UUID | str | None = None,
) -> str:
    """Create or update a memory for the given user."""
    user = User.objects.get(pk=user_id)
    mem_uuid = UUID(str(memory_id)) if memory_id else uuid4()
    embedding_text = f"{content}\n{context}".strip()
    embedding = _embed_text(embedding_text)

    memory, _created = UserMemory.objects.update_or_create(
        memory_id=mem_uuid,
        defaults={
            "user": user,
            "content": content,
            "context": context,
            "embedding": embedding,
        },
    )
    return f"Stored memory {memory.memory_id}"


def search_memories(
    *,
    user_id: str,
    query: str,
    limit: int = 10,
) -> list[MemoryRecord]:
    """Return the most relevant memories for a user, ranked by embedding similarity."""
    memories = list(UserMemory.objects.filter(user_id=user_id))
    if not memories:
        return []

    query_embedding = _embed_text(query)
    scored: list[tuple[float, UserMemory]] = []
    for memory in memories:
        if not memory.embedding:
            continue
        score = _cosine_similarity(query_embedding, memory.embedding)
        scored.append((score, memory))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        MemoryRecord(
            memory_id=str(memory.memory_id),
            content=memory.content,
            context=memory.context,
            score=score,
        )
        for score, memory in scored[:limit]
    ]


def list_memories(*, user_id: str) -> list[MemoryRecord]:
    """Return all memories for a user, newest first."""
    memories = UserMemory.objects.filter(user_id=user_id).order_by("-updated_at")
    return [
        MemoryRecord(
            memory_id=str(memory.memory_id),
            content=memory.content,
            context=memory.context,
        )
        for memory in memories
    ]


def delete_memory(*, user_id: str, memory_id: str) -> bool:
    deleted, _ = UserMemory.objects.filter(
        user_id=user_id,
        memory_id=memory_id,
    ).delete()
    return deleted > 0


def format_memories_for_prompt(memories: list[MemoryRecord]) -> str:
    """Format retrieved memories for inclusion in the agent system prompt."""
    if not memories:
        return ""

    lines = []
    for memory in memories:
        line = f"[{memory.memory_id}]: {memory.content}"
        if memory.context:
            line += f" (context: {memory.context})"
        if memory.score is not None:
            line += f" (similarity: {memory.score:.2f})"
        lines.append(line)

    return "\n".join(lines)
