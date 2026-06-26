"""Agent tool for persisting user memories across conversations."""

from uuid import UUID

from asgiref.sync import sync_to_async
from langchain_core.tools import StructuredTool

from ..services.memory import upsert_memory as persist_memory

_TOOL_DESCRIPTION = """Save or update a memory about the user for future conversations.

Use this when the user shares preferences, personal facts, or other details
worth remembering across chat sessions. If a memory conflicts with an existing
one, update it by passing memory_id instead of creating a duplicate. If the
user corrects a memory, update the existing entry.

Args:
    content: The main content of the memory, e.g. "User prefers concise answers."
    context: Additional context, e.g. "Mentioned while discussing report summaries."
    memory_id: Only provide when updating an existing memory.
"""


def make_upsert_memory_tool(user_id: str) -> StructuredTool:
    """Return a user-scoped memory tool bound to the authenticated user."""

    async def _save(
        content: str,
        context: str = "",
        memory_id: str | None = None,
    ) -> str:
        parsed_id: UUID | None = UUID(memory_id) if memory_id else None
        return await sync_to_async(persist_memory)(
            user_id=user_id,
            content=content,
            context=context,
            memory_id=parsed_id,
        )

    return StructuredTool.from_function(
        coroutine=_save,
        name="upsert_memory",
        description=_TOOL_DESCRIPTION,
    )
