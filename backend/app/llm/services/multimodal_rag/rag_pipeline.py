import logging
from base64 import b64decode
from typing import TypedDict
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from langgraph.graph import StateGraph

load_dotenv()

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


class ProcessingState(TypedDict):
    """State for PDF processing workflow"""
    file_path: str
    chunks: list
    summaries: dict[str, list[str]]
    vector_db: VectorDBWrapper
    object_store: S3Wrapper


class ChatState(TypedDict):
    """State for chat/query workflow"""
    messages: list[HumanMessage | SystemMessage]
    context: dict[str, list[Document]]
    current_response: str
    vector_db: VectorDBWrapper
    object_store: S3Wrapper


def pre_process_pdf(state: ProcessingState) -> ProcessingState:
    """Pre-process the PDF file"""
    try:
        # Upload PDF to S3
        state["object_store"].upload_file(
            file_path=state["file_path"],
            object_name=f"pdfs/{uuid4()!s}.pdf",
        )

        # Process PDF
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
        model = ChatOpenAI(temperature=0.5, model_name="gpt-4")
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
        state["summaries"]["images"] = image_chain.batch(images, {"max_concurrency": 2})

        return state
    except Exception as e:
        logger.error(f"Error summarizing content: {e!s}")
        raise


def load_summaries(state: ProcessingState) -> ProcessingState:
    """Load summaries into vector store with links to original content"""
    try:
        vector_db = state["vector_db"]
        id_key = "source_id"

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
            Document(page_content=summary, metadata={id_key: doc_ids[i]})
            for i, summary in clean_text_summaries
        ]
        if summary_texts:
            vector_db.vector_store.add_documents(summary_texts)
            # Store text content directly in metadata
            for i, _ in clean_text_summaries:
                vector_db.vector_store.add_documents(
                    [Document(page_content=texts[i], metadata={id_key: doc_ids[i]})],
                )

        # Add table summaries
        summary_tables = [
            Document(page_content=summary, metadata={id_key: table_ids[i]})
            for i, summary in clean_table_summaries
        ]
        if summary_tables:
            vector_db.vector_store.add_documents(summary_tables)
            # Store table content directly in metadata
            for i, _ in clean_table_summaries:
                vector_db.vector_store.add_documents(
                    [Document(page_content=tables[i], metadata={id_key: table_ids[i]})],
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
                    metadata={id_key: img_id, "image_key": img_key},
                ),
            )

        if summary_img:
            vector_db.vector_store.add_documents(summary_img)

        return state
    except Exception as e:
        logger.error(f"Error loading summaries: {e!s}")
        raise


def parse_docs(docs, object_store):
    """Split image URLs and texts, generating fresh presigned URLs for images"""
    urls = []
    text = []
    for doc in docs:
        if "image_key" in doc.metadata:
            # Generate fresh presigned URL from stored S3 key
            img_key = doc.metadata["image_key"]
            url = object_store.generate_presigned_url(
                object_name=img_key,
                expiration=3600,
            )
            urls.append(url)
        else:
            text.append(doc.page_content)
    return {"images": urls, "texts": text}


def build_prompt(kwargs):
    """Build prompt with text and image context"""
    docs_by_type = kwargs["context"]
    user_question = kwargs["question"]

    context_text = ""
    if len(docs_by_type["texts"]) > 0:
        for text_element in docs_by_type["texts"]:
            context_text += text_element

    prompt_template = f"""
    Answer the question based only on the following context, which can include text, tables, and the below image.
    Context: {context_text}
    Question: {user_question}
    """

    prompt_content = [{"type": "text", "text": prompt_template}]

    # if len(docs_by_type["images"]) > 0:
    #     for image_url in docs_by_type["images"]:
    #         prompt_content.append(
    #             {
    #                 "type": "image_url",
    #                 "image_url": {"url": image_url},
    #             }
    #         )

    return ChatPromptTemplate.from_messages([HumanMessage(content=prompt_content)])


def retrieve_and_generate(state: ChatState) -> ChatState:
    """Retrieve context and generate response using retrieved context"""
    try:
        # Retrieve context
        vector_db = state["vector_db"]
        query = state["messages"][-1].content
        docs = vector_db.similarity_search(query)
        parsed_docs = parse_docs(docs=docs, object_store=state["object_store"])
        state["context"] = parsed_docs

        # Check if we have any relevant context
        if (
            not parsed_docs["texts"]
            and not parsed_docs["images"]
            and not parsed_docs["tables"]
        ):
            state["current_response"] = (
                "I don't have enough context to answer your question. Please try asking something related to the documents that have been processed."
            )
            return state

        chain_with_sources = {
            "context": lambda x: parsed_docs,
            "question": RunnablePassthrough(),
        } | RunnablePassthrough().assign(
            response=(
                RunnableLambda(build_prompt)
                | ChatOpenAI(model="gpt-4o-mini")
                | StrOutputParser()
            ),
        )

        result = chain_with_sources.invoke(state["messages"][-1].content)
        state["current_response"] = result
        return state
    except Exception as e:
        logger.error(f"State ==> {state}")
        logger.error(f"Error retrieving context or generating response: {e!s}")
        raise


def create_processing_graph() -> StateGraph:
    """Create graph for initial PDF processing"""
    workflow = StateGraph(ProcessingState)
    workflow.add_node("preprocess", pre_process_pdf)
    workflow.add_node("summarize", summarize_content)
    workflow.add_node("load_summaries", load_summaries)

    workflow.set_entry_point("preprocess")
    workflow.add_edge("preprocess", "summarize")
    workflow.add_edge("summarize", "load_summaries")
    workflow.add_edge("load_summaries", END)

    return workflow.compile()


def create_chat_graph() -> StateGraph:
    """Create graph for question answering"""
    workflow = StateGraph(ChatState)
    workflow.add_node("retrieve_and_generate", retrieve_and_generate)

    workflow.set_entry_point("retrieve_and_generate")
    workflow.add_edge("retrieve_and_generate", END)

    return workflow.compile()


def create_processing_state(file_path: str) -> ProcessingState:
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
        "chunks": [],
        "summaries": {},
        "vector_db": VectorDBWrapper(),
        "object_store": S3Wrapper(),
    }


def create_chat_state(question: str) -> ChatState:
    """
    Create initial state for chat queries.

    Args:
        question: User's question to answer

    Returns:
        ChatState: Initial state dictionary for chat workflow

    Raises:
        RuntimeError: If the vector DB is not initialized
    """
    return {
        "messages": [HumanMessage(content=question)],
        "context": {},
        "current_response": "",
        "vector_db": VectorDBWrapper(),
        "object_store": S3Wrapper(),
    }
