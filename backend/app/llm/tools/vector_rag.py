import json
import logging

from langchain_core.tools import StructuredTool

from ...llm.utils.s3 import S3Wrapper
from ...llm.utils.vector_db import VectorDBWrapper

logger = logging.getLogger(__name__)

_NO_CONTEXT_MSG = "No relevant context found in the knowledge base."

_TOOL_DESCRIPTION = """Retrieve relevant context from the vector store for a given question.

Use this tool to fetch document context before answering questions that require
information from ingested documents. Returns the retrieved text chunks and image
data so the agent can generate a grounded answer.

Args:
    question: The user question to retrieve context for.

Returns:
    Retrieved context as a string, or a message indicating nothing was found.
"""


def _format_chunk(doc, object_store: S3Wrapper) -> str | None:
    """Build a context chunk, swapping image_key for a presigned URL when present."""
    image_key = doc.metadata.get("image_key")
    chunk = doc.model_dump()
    if image_key:
        url = object_store.generate_presigned_url(object_name=image_key)
        if url:
            chunk.pop("id")
            chunk["metadata"]["image_url"] = url
            chunk["metadata"].pop("image_key")
            chunk["metadata"].pop("_collection_name", None)
            chunk["metadata"].pop("_id", None)

    return chunk


def _parse_docs(docs, object_store: S3Wrapper) -> list[str]:
    """Turn retrieved docs into context chunks with presigned image URLs inlined."""
    chunks: list[dict] = []
    for doc in docs:
        chunk = _format_chunk(doc=doc, object_store=object_store)
        if chunk:
            chunks.append(chunk)
    return chunks


def make_vector_rag_tool(*, document_id: int | None = None) -> StructuredTool:
    """Return a retrieval tool, optionally scoped to one document."""

    def _retrieve(question: str) -> str:
        try:
            vector_db = VectorDBWrapper()
            object_store = S3Wrapper()

            docs = vector_db.similarity_search(question, document_id=document_id)
            chunks = _parse_docs(docs=docs, object_store=object_store)

            if not chunks:
                return _NO_CONTEXT_MSG

            return json.dumps(chunks)

        except Exception as e:
            logger.error(f"Error in vector_rag_tool: {e!s}")
            raise

    return StructuredTool.from_function(
        func=_retrieve,
        name="vector_rag_tool",
        description=_TOOL_DESCRIPTION,
    )


vector_rag_tool = make_vector_rag_tool()
