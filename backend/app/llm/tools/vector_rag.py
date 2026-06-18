import logging
from base64 import b64encode

from langchain_core.tools import tool

from ...llm.utils.s3 import S3Wrapper
from ...llm.utils.vector_db import VectorDBWrapper

logger = logging.getLogger(__name__)

_NO_CONTEXT_MSG = "No relevant context found in the knowledge base."


def _parse_docs(docs, object_store: S3Wrapper) -> dict[str, list]:
    """Split retrieved docs into text chunks and base64 image data URLs."""
    images = []
    texts = []
    for doc in docs:
        if "image_key" in doc.metadata:
            img_bytes = object_store.get_file(object_name=doc.metadata["image_key"])
            if img_bytes:
                b64 = b64encode(img_bytes).decode("utf-8")
                images.append(f"data:image/jpeg;base64,{b64}")
        else:
            texts.append(doc.page_content)
    return {"images": images, "texts": texts}


@tool
def vector_rag_tool(question: str) -> str:
    """Retrieve relevant context from the vector store for a given question.

    Use this tool to fetch document context before answering questions that require
    information from ingested documents. Returns the retrieved text chunks and image
    data so the agent can generate a grounded answer.

    Args:
        question: The user question to retrieve context for.

    Returns:
        Retrieved context as a string, or a message indicating nothing was found.
    """
    try:
        vector_db = VectorDBWrapper()
        object_store = S3Wrapper()

        docs = vector_db.similarity_search(question)
        parsed_docs = _parse_docs(docs=docs, object_store=object_store)

        if not parsed_docs["texts"] and not parsed_docs["images"]:
            return _NO_CONTEXT_MSG

        parts = parsed_docs["texts"]
        # TODO: Add image support
        # if parsed_docs["images"]:
        #     parts = parts + [f"[image:{url}]" for url in parsed_docs["images"]]

        return "\n\n".join(parts)

    except Exception as e:
        logger.error(f"Error in vector_rag_tool: {e!s}")
        raise
