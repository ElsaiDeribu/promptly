import logging
from base64 import b64decode
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

from ....llm.utils.pdf_processor import get_images_base64
from ....llm.utils.pdf_processor import get_tables
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
    chunks: list
    summaries: dict[str, list[str]]
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
        "summaries": {},
        "vector_db": VectorDBWrapper(),
        "object_store": S3Wrapper(),
    }


def _chunk_metadata(state: ProcessingState, source_id: str, **extra: str | int) -> dict[str, str | int]:
    metadata: dict[str, str | int] = {"source_id": source_id}
    if document_id := state.get("document_id"):
        metadata["document_id"] = document_id
    if filename := state.get("original_filename"):
        metadata["original_filename"] = filename
    metadata.update(extra)
    return metadata


# ============================================================
# PDF Processing Workflow
# ============================================================
def pre_process_pdf(state: ProcessingState) -> ProcessingState:
    """Parse the PDF file (already stored in S3 via presigned upload)."""
    try:
        state["chunks"] = process_pdf(state["file_path"])
        state["summaries"] = {"text": [], "tables": [], "images": []}
        if "vector_db" not in state:
            state["vector_db"] = VectorDBWrapper()

        return state

    except Exception as e:
        logger.error(f"Error pre-processing PDF: {e!s}")
        raise


def summarize_content(state: ProcessingState) -> ProcessingState:
    """Summarize text, tables and images from the PDF"""
    try:
        # Extract content
        texts = [chunk.text for chunk in state["chunks"] if hasattr(chunk, "text")]
        tables = get_tables(state["chunks"])
        images = get_images_base64(state["chunks"])

        # Text/table summary prompt
        text_prompt = ChatPromptTemplate.from_template(
            """
            You are an assistant tasked with summarizing content.
            Give a concise summary of the following content.
            Respond only with the summary, no additional comments.
            Content: {element}
        """,
        )

        # Create summary chain
        model = ChatOpenAI(temperature=0.5, model="gpt-4")
        summary_chain = (
            {"element": lambda x: x} | text_prompt | model | StrOutputParser()
        )

        # Summarize text and tables
        state["summaries"]["text"] = summary_chain.batch(texts, {"max_concurrency": 5})
        state["summaries"]["tables"] = summary_chain.batch(
            tables, {"max_concurrency": 5},
        )

        # Image summary prompt
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

        # Create image chain
        image_chain = image_prompt | ChatOpenAI(model="gpt-4o") | StrOutputParser()

        # Summarize images
        state["summaries"]["images"] = image_chain.batch(
            [{"image": image} for image in images],
            {"max_concurrency": 2},
        )

        return state
    except Exception as e:
        logger.error(f"Error summarizing content: {e!s}")
        raise


def load_summaries(state: ProcessingState) -> ProcessingState:
    """Load summaries into vector store with links to original content"""
    try:
        vector_db = state["vector_db"]

        # Get content and summaries
        texts = [chunk.text for chunk in state["chunks"] if hasattr(chunk, "text")]
        tables = get_tables(state["chunks"])
        images = get_images_base64(state["chunks"])

        text_summaries = state["summaries"]["text"]
        table_summaries = state["summaries"]["tables"]
        image_summaries = state["summaries"]["images"]

        # Generate unique IDs
        doc_ids = [str(uuid4()) for _ in texts]
        table_ids = [str(uuid4()) for _ in tables]
        img_ids = [str(uuid4()) for _ in images]

        # Clean summaries
        clean_text_summaries = [
            (i, s) for i, s in enumerate(text_summaries) if s and s.strip()
        ]
        clean_table_summaries = [
            (i, s) for i, s in enumerate(table_summaries) if s and s.strip()
        ]
        clean_image_summaries = [
            (i, s) for i, s in enumerate(image_summaries) if s and s.strip()
        ]

        logger.info(f"Text summaries: {len(clean_text_summaries)}")
        logger.info(f"Table summaries: {len(clean_table_summaries)}")
        logger.info(f"Image summaries: {len(clean_image_summaries)}")

        # Add text summaries
        summary_texts = [
            Document(
                page_content=summary,
                metadata=_chunk_metadata(state, doc_ids[i], content_type="text"),
            )
            for i, summary in clean_text_summaries
        ]
        if summary_texts:
            vector_db.vector_store.add_documents(summary_texts)
            # Store text content directly in metadata
            for i, _ in clean_text_summaries:
                vector_db.vector_store.add_documents(
                    [
                        Document(
                            page_content=texts[i],
                            metadata=_chunk_metadata(state, doc_ids[i], content_type="text"),
                        ),
                    ],
                )

        # Add table summaries
        summary_tables = [
            Document(
                page_content=summary,
                metadata=_chunk_metadata(state, table_ids[i], content_type="table"),
            )
            for i, summary in clean_table_summaries
        ]
        if summary_tables:
            vector_db.vector_store.add_documents(summary_tables)
            # Store table content directly in metadata
            for i, _ in clean_table_summaries:
                vector_db.vector_store.add_documents(
                    [
                        Document(
                            page_content=tables[i],
                            metadata=_chunk_metadata(state, table_ids[i], content_type="table"),
                        ),
                    ],
                )

        # Add image summaries and save images to MinIO
        summary_img = []
        for i, summary in clean_image_summaries:
            # Save image to MinIO
            img_id = img_ids[i]
            img_key = f"images/{img_id}.jpg"

            # Convert base64 to bytes and upload
            img_bytes = b64decode(images[i])
            state["object_store"].put_file(
                data=img_bytes,
                object_name=img_key,
                content_type="image/jpeg",
            )

            # Store the S3 key instead of presigned URL (generate URL at query time)
            summary_img.append(
                Document(
                    page_content=summary,
                    metadata=_chunk_metadata(
                        state,
                        img_id,
                        content_type="image",
                        image_key=img_key,
                    ),
                ),
            )

        if summary_img:
            vector_db.vector_store.add_documents(summary_img)

        return state
    except Exception as e:
        logger.error(f"Error loading summaries: {e!s}")
        raise


def create_processing_graph() -> CompiledStateGraph:
    """Create graph for initial PDF processing"""
    workflow = StateGraph(ProcessingState)
    workflow.add_node("preprocess", pre_process_pdf)
    workflow.add_node("summarize", summarize_content)
    workflow.add_node("load_summaries", load_summaries)

    workflow.add_edge(START, "preprocess")
    workflow.add_edge("preprocess", "summarize")
    workflow.add_edge("summarize", "load_summaries")
    workflow.add_edge("load_summaries", END)

    return workflow.compile(name="rag_pdf_processing").with_config(
        {"run_name": "rag_pdf_processing"},
    )

