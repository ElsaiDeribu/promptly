import logging
from base64 import b64encode
from typing import Any
from typing import TypedDict
from uuid import uuid4

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from langgraph.graph import START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from ....llm.utils.pdf_processor import ProcessedChunk
from ....llm.utils.pdf_processor import process_pdf
from ....llm.utils.s3 import S3Wrapper
from ....llm.utils.vector_db import VectorDBWrapper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# State Definitions
# ============================================================
class ProcessingState(TypedDict, total=False):
    """State for PDF processing workflow"""

    file_path: str
    document_id: int
    original_filename: str
    chunks: list[ProcessedChunk]
    vector_db: VectorDBWrapper
    object_store: S3Wrapper


def create_processing_state(
    file_path: str,
    *,
    document_id: int | None = None,
    original_filename: str | None = None,
) -> ProcessingState:
    """
    Create initial state for PDF processing.

    Args:
        file_path: Path to the PDF file to process

    Returns:
        ProcessingState: Initial state dictionary for processing workflow

    Raises:
        RuntimeError: If the vector DB is not initialized
    """
    return {
        "file_path": file_path,
        "document_id": document_id,
        "original_filename": original_filename or "",
        "vector_db": VectorDBWrapper(),
        "object_store": S3Wrapper(),
    }


def _chunks_by_type(
    chunks: list[ProcessedChunk],
    content_type: str,
) -> list[ProcessedChunk]:
    return [chunk for chunk in chunks if chunk.content_type == content_type]


def _chunks_with_image_bytes(chunks: list[ProcessedChunk]) -> list[ProcessedChunk]:
    return [chunk for chunk in chunks if chunk.image_bytes]


def _chunk_metadata(
    state: ProcessingState,
    source_id: str,
    *,
    provenance: dict[str, Any] | None = None,
    **extra: str | int,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source_id": source_id}
    if document_id := state.get("document_id"):
        metadata["document_id"] = document_id
    if filename := state.get("original_filename"):
        metadata["original_filename"] = filename
    if provenance:
        metadata.update(provenance)
    metadata.update(extra)
    return metadata


def _chunks_to_documents(
    state: ProcessingState,
    chunks: list[ProcessedChunk],
    content_type: str,
) -> list[Document]:
    return [
        Document(
            page_content=chunk.text,
            metadata=_chunk_metadata(
                state,
                str(uuid4()),
                provenance=chunk.provenance,
                content_type=content_type,
            ),
        )
        for chunk in chunks
        if chunk.text.strip()
    ]


def describe_image_chunks(image_chunks: list[ProcessedChunk]) -> list[str]:
    """Generate vision descriptions for image chunks that include image_bytes."""
    images_b64 = [b64encode(chunk.image_bytes).decode() for chunk in image_chunks]
    if not images_b64:
        return []

    image_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "user",
                [
                    {
                        "type": "text",
                        "text": "Describe this image concisely and technically.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64,{image}"},
                    },
                ],
            ),
        ],
    )

    image_chain = image_prompt | ChatOpenAI(model="gpt-4o") | StrOutputParser()
    return image_chain.batch(
        [{"image": image} for image in images_b64],
        {"max_concurrency": 2},
    )


# ============================================================
# PDF Processing Workflow
# ============================================================
def pre_process_pdf(state: ProcessingState) -> ProcessingState:
    """Parse the PDF file (already stored in S3 via presigned upload)."""
    try:
        state["chunks"] = process_pdf(state["file_path"])
        return state

    except Exception as e:
        logger.error(f"Error pre-processing PDF: {e!s}")
        raise


def index_chunks(state: ProcessingState) -> ProcessingState:
    """Describe images, store assets, and index all chunks in the vector store."""
    try:
        vector_db = state["vector_db"]
        chunks = state["chunks"]
        text_chunks = _chunks_by_type(chunks, "text")
        table_chunks = _chunks_by_type(chunks, "table")
        image_chunks_with_bytes = _chunks_with_image_bytes(
            _chunks_by_type(chunks, "image"),
        )
        image_summaries = describe_image_chunks(image_chunks_with_bytes)

        documents: list[Document] = []

        text_docs = _chunks_to_documents(state, text_chunks, "text")
        table_docs = _chunks_to_documents(state, table_chunks, "table")

        image_doc_count = 0
        for chunk, summary in zip(
            image_chunks_with_bytes,
            image_summaries,
            strict=True,
        ):
            if not summary or not summary.strip():
                continue

            image_doc_count += 1
            img_id = str(uuid4())
            img_key = f"images/{img_id}.jpg"

            state["object_store"].put_file(
                data=chunk.image_bytes,
                object_name=img_key,
                content_type="image/jpeg",
            )

            documents.append(
                Document(
                    page_content=summary,
                    metadata=_chunk_metadata(
                        state,
                        img_id,
                        provenance=chunk.provenance,
                        content_type="image",
                        image_key=img_key,
                    ),
                ),
            )

        logger.info("Text chunks: %s", len(text_docs))
        logger.info("Table chunks: %s", len(table_docs))
        logger.info("Image summaries: %s", image_doc_count)

        documents.extend(text_docs)
        documents.extend(table_docs)

        if documents:
            vector_db.vector_store.add_documents(documents)

        return state
    except Exception as e:
        logger.error(f"Error indexing chunks: {e!s}")
        raise


def create_processing_graph() -> CompiledStateGraph:
    """Create graph for initial PDF processing"""
    workflow = StateGraph(ProcessingState)
    workflow.add_node("preprocess", pre_process_pdf)
    workflow.add_node("index", index_chunks)

    workflow.add_edge(START, "preprocess")
    workflow.add_edge("preprocess", "index")
    workflow.add_edge("index", END)

    return workflow.compile(name="rag_pdf_processing").with_config(
        {"run_name": "rag_pdf_processing"},
    )
