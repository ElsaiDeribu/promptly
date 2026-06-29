from datetime import datetime

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from ..tools.memory import make_upsert_memory_tool
from ..tools.vector_rag import make_vector_rag_tool

_BASE_PROMPT = (
    "You are a helpful assistant that answers questions about documents and "
    "remembers user preferences across conversations.\n\n"
    "For document questions: use vector_rag_tool to retrieve context from the "
    "knowledge base before answering. When the user refers to earlier turns, "
    "formulate a standalone search query for the tool from the conversation. "
    "Base document answers strictly on the retrieved context. If the tool returns "
    "no useful context, tell the user you don't have enough information.\n\n"
    "For personal preferences and facts about the user: use upsert_memory immediately. "
    "Do not use vector_rag_tool for saving preferences or personal information. "
    "If the user corrects a saved memory, update it by passing the existing "
    "memory_id. Use saved memories below to personalize responses when relevant."
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def build_rag_agent(
    *,
    user_id: str,
    memory_context: str = "",
    document_id: int | None = None,
):
    """Build a ReAct agent with user-scoped memory tools and optional context."""
    prompt_parts = [_BASE_PROMPT]
    if memory_context:
        prompt_parts.append(f"\n\nSaved user memories:\n{memory_context}")

    prompt_parts.append(f"\n\nSystem time: {datetime.now().isoformat()}")
    system_prompt = SystemMessage(content="".join(prompt_parts))

    return create_react_agent(
        model=_llm,
        tools=[
            make_vector_rag_tool(document_id=document_id),
            make_upsert_memory_tool(user_id),
        ],
        prompt=system_prompt,
    )
