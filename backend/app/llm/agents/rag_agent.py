from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from ..tools.vector_rag import vector_rag_tool

_SYSTEM_PROMPT = SystemMessage(
    content=(
        "You are a helpful assistant that answers questions about documents. "
        "Always use the vector_rag_tool to retrieve relevant context from the "
        "knowledge base before answering. Base your answers strictly on the "
        "retrieved context. If the tool returns no useful context, tell the user "
        "you don't have enough information to answer their question."
    )
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

rag_agent = create_react_agent(
    model=_llm,
    tools=[vector_rag_tool],
    prompt=_SYSTEM_PROMPT,
)
