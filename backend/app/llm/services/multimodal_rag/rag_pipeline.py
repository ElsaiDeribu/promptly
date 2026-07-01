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
        "chunks": [],
        "vector_db": VectorDBWrapper(),
        "object_store": S3Wrapper(),
    }


def _chunks_by_type(
    chunks: list[ProcessedChunk],
    content_type: str,
) -> list[ProcessedChunk]:
    return [chunk for chunk in chunks if chunk.content_type == content_type]


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


def describe_image_chunks(image_chunks: list[ProcessedChunk]) -> list[str]:
    """Generate vision descriptions for image chunks."""
    images_b64 = [
        b64encode(chunk.image_bytes).decode()
        for chunk in image_chunks
        if chunk.image_bytes
    ]
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
        if "vector_db" not in state:
            state["vector_db"] = VectorDBWrapper()

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
        image_chunks = _chunks_by_type(chunks, "image")

        image_chunk_indexes = [
            index
            for index, chunk in enumerate(image_chunks)
            if chunk.image_bytes
        ]
        image_summaries = describe_image_chunks(image_chunks)

        documents: list[Document] = []

        text_docs = [
            Document(
                page_content=chunk.text,
                metadata=_chunk_metadata(
                    state,
                    str(uuid4()),
                    provenance=chunk.provenance,
                    content_type="text",
                ),
            )
            for chunk in text_chunks
            if chunk.text.strip()
        ]
        table_docs = [
            Document(
                page_content=chunk.text,
                metadata=_chunk_metadata(
                    state,
                    str(uuid4()),
                    provenance=chunk.provenance,
                    content_type="table",
                ),
            )
            for chunk in table_chunks
            if chunk.text.strip()
        ]

        clean_image_summaries = [
            (i, s) for i, s in enumerate(image_summaries) if s and s.strip()
        ]

        logger.info("Text chunks: %s", len(text_docs))
        logger.info("Table chunks: %s", len(table_docs))
        logger.info("Image summaries: %s", len(clean_image_summaries))

        documents.extend(text_docs)
        documents.extend(table_docs)

        for summary_index, summary in clean_image_summaries:
            chunk_index = image_chunk_indexes[summary_index]
            chunk = image_chunks[chunk_index]
            image_bytes = chunk.image_bytes
            if image_bytes is None:
                continue

            img_id = str(uuid4())
            img_key = f"images/{img_id}.jpg"

            state["object_store"].put_file(
                data=image_bytes,
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
