import logging
import os
from base64 import b64decode
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

import boto3
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import Qdrant
from langgraph.graph import END, StateGraph
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

load_dotenv()

from typing import List

from unstructured.documents.elements import Element
from unstructured.partition.pdf import partition_pdf

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import streamlit as st

# ============================================================


# ------------------------------------------------------------
# Vector Database
# ------------------------------------------------------------
class VectorDBWrapper:
    """Wrapper class for vector database operations to make it easy to swap implementations"""

    def __init__(self, embeddings: Optional[OpenAIEmbeddings] = None):
        """Initialize the vector store wrapper

        Args:
            embeddings: Optional embeddings model, defaults to OpenAIEmbeddings if not provided
        """
        self.embeddings = embeddings if embeddings else OpenAIEmbeddings()

        # Get Qdrant connection details from environment
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", 6333))

        # Initialize Qdrant client
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)

        # Initialize MinIO client
        self.s3_client = boto3.client(
            "s3",
            endpoint_url="http://minio:9000",
            aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            region_name="us-east-1",
        )

        # Create bucket if it doesn't exist
        bucket_name = "pdf-images"
        # try:
        #     self.s3_client.head_bucket(Bucket=bucket_name)
        # except:
        #     self.s3_client.create_bucket(Bucket=bucket_name)

        self.bucket_name = bucket_name

        # Create collection if it doesn't exist
        try:
            self.client.get_collection("multi_modal_rag")
        except Exception:
            # Create new collection with specified vectors configuration
            self.client.create_collection(
                collection_name="multi_modal_rag",
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

        # Initialize vectorstore
        self.vector_store = Qdrant(
            client=self.client,
            collection_name="multi_modal_rag",
            embeddings=self.embeddings,
        )

    def add_documents(self, documents: List[Document]) -> None:
        """Add documents to vector store

        Args:
            documents: List of Documents to add
        """
        # Add to vectorstore
        self.vector_store.add_documents(documents)

    def similarity_search(self, query: str, k: int = 4) -> List[Document]:
        """Perform similarity search for a query

        Args:
            query: The search query
            k: Number of results to return

        Returns:
            List of relevant documents
        """
        return self.vector_store.similarity_search(query, k=k)

    def save_local(self, path: str) -> None:
        """Save the vector store to local storage

        Note: With Qdrant this is not needed as data is automatically persisted
        """
        pass  # Qdrant automatically persists data

    def load_local(self, path: str) -> None:
        """Load the vector store from local storage

        Note: With Qdrant this is not needed as data is automatically persisted
        """
        pass  # Qdrant automatically loads persisted data


# ------------------------------------------------------------
# Pre-processing
# ------------------------------------------------------------
def process_pdf(file_path: str, output_path: str = "./output/") -> List[Element]:
    """Process a PDF file and extract chunks with tables and images.

    Args:
        file_path: Path to the PDF file to process
        output_path: Directory to save extracted content (default: "./output/")

    Returns:
        List of document elements containing the extracted chunks
    """
    # Reference: https://docs.unstructured.io/open-source/core-functionality/chunking
    chunks = partition_pdf(
        filename=file_path,
        infer_table_structure=True,  # extract tables
        strategy="hi_res",  # mandatory to infer tables
        extract_image_block_types=[
            "Image"
        ],  # Add 'Table' to list to extract image of tables
        # image_output_dir_path=output_path,   # if None, images and tables will saved in base64
        extract_image_block_to_payload=True,  # if true, will extract base64 for API usage
        chunking_strategy="by_title",  # or 'basic'
        max_characters=10000,  # defaults to 500
        combine_text_under_n_chars=2000,  # defaults to 0
        new_after_n_chars=6000,
        # extract_images_in_pdf=True,          # deprecated
    )

    return chunks


# ------------------------------------------------------------
# Utils
# ------------------------------------------------------------
# Get the images from the CompositeElement objects
def get_images_base64(chunks):
    images_b64 = []
    for chunk in chunks:
        if "CompositeElement" in str(type(chunk)):
            chunk_els = chunk.metadata.orig_elements
            for el in chunk_els:
                if "Image" in str(type(el)):
                    images_b64.append(el.metadata.image_base64)
    return images_b64


# Get the tables from the CompositeElement objects
def get_tables(chunks):
    tables = []
    for chunk in chunks:
        if "CompositeElement" in str(type(chunk)):
            chunk_els = chunk.metadata.orig_elements
            for el in chunk_els:
                if "Table" in str(type(el)):
                    tables.append(el.text)
    return tables


# Define state schema
class GraphState(TypedDict):
    messages: List[HumanMessage | SystemMessage]
    context: Dict[str, List[Document]]
    current_response: str
    file_path: str
    chunks: List
    summaries: Dict[str, List[str]]
    vector_db: VectorDBWrapper


def pre_process_pdf(state: GraphState) -> GraphState:
    """Pre-process the PDF file"""
    try:
        state["chunks"] = process_pdf(state["file_path"])
        state["summaries"] = {"text": [], "tables": [], "images": []}
        if "vector_db" not in state:
            state["vector_db"] = VectorDBWrapper()
        return state
    except Exception as e:
        logger.error(f"Error pre-processing PDF: {str(e)}")
        raise


def summarize_content(state: GraphState) -> GraphState:
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
        """
        )

        # Create summary chain
        model = ChatOpenAI(temperature=0.5, model_name="gpt-4")
        summary_chain = (
            {"element": lambda x: x} | text_prompt | model | StrOutputParser()
        )

        # Summarize text and tables
        state["summaries"]["text"] = summary_chain.batch(texts, {"max_concurrency": 5})
        state["summaries"]["tables"] = summary_chain.batch(
            tables, {"max_concurrency": 5}
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
                )
            ]
        )

        # Create image chain
        image_chain = image_prompt | ChatOpenAI(model="gpt-4o") | StrOutputParser()

        # Summarize images
        state["summaries"]["images"] = image_chain.batch(images, {"max_concurrency": 2})

        return state
    except Exception as e:
        logger.error(f"Error summarizing content: {str(e)}")
        raise


def load_summaries(state: GraphState) -> GraphState:
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
                    [Document(page_content=texts[i], metadata={id_key: doc_ids[i]})]
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
                    [Document(page_content=tables[i], metadata={id_key: table_ids[i]})]
                )

        # Add image summaries and save images to MinIO
        summary_img = []
        for i, summary in clean_image_summaries:
            # Save image to MinIO
            img_id = img_ids[i]
            img_key = f"images/{img_id}.jpg"

            # Convert base64 to bytes and upload
            img_bytes = b64decode(images[i])
            vector_db.s3_client.put_object(
                Bucket=vector_db.bucket_name,
                Key=img_key,
                Body=img_bytes,
                ContentType="image/jpeg",
            )

            # Store the S3 key instead of presigned URL (generate URL at query time)
            summary_img.append(
                Document(
                    page_content=summary, metadata={id_key: img_id, "image_key": img_key}
                )
            )

        if summary_img:
            vector_db.vector_store.add_documents(summary_img)

        return state
    except Exception as e:
        logger.error(f"Error loading summaries: {str(e)}")
        raise


def parse_docs(docs, vector_db):
    """Split image URLs and texts, generating fresh presigned URLs for images"""
    urls = []
    text = []
    for doc in docs:
        if "image_key" in doc.metadata:
            # Generate fresh presigned URL from stored S3 key
            img_key = doc.metadata["image_key"]
            url = vector_db.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": vector_db.bucket_name, "Key": img_key},
                ExpiresIn=3600,  # 1 hour expiration
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


def retrieve_and_generate(state: GraphState) -> GraphState:
    """Retrieve context and generate response using retrieved context"""
    try:
        # Retrieve context
        vector_db = state["vector_db"]
        query = state["messages"][-1].content
        docs = vector_db.similarity_search(query)
        parsed_docs = parse_docs(docs, vector_db)
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
            )
        )

        result = chain_with_sources.invoke(state["messages"][-1].content)
        state["current_response"] = result
        return state
    except Exception as e:
        logger.error(f"State ==> {state}")
        logger.error(f"Error retrieving context or generating response: {str(e)}")
        raise


def create_processing_graph() -> StateGraph:
    """Create graph for initial PDF processing"""
    workflow = StateGraph(GraphState)
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
    workflow = StateGraph(GraphState)
    workflow.add_node("retrieve_and_generate", retrieve_and_generate)

    workflow.set_entry_point("retrieve_and_generate")
    workflow.add_edge("retrieve_and_generate", END)

    return workflow.compile()


def main():
    st.title("PDF Processor RAG Pipeline")

    # Initialize session state for vector_db and processed_files
    if "vector_db" not in st.session_state:
        st.session_state.vector_db = VectorDBWrapper()
    if "processed_files" not in st.session_state:
        st.session_state.processed_files = set()
    if "temp_file_path" not in st.session_state:
        st.session_state.temp_file_path = None

    # PDF upload section
    with st.expander("Upload New PDF (Optional)"):
        uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

        if uploaded_file is not None:
            # Create input directory if it doesn't exist
            os.makedirs("./input", exist_ok=True)

            # Save uploaded file to a temporary location
            temp_path = f"./input/{uploaded_file.name}"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.session_state.temp_file_path = temp_path
            st.success(f"Uploaded {uploaded_file.name}")

            # Add process button
            if st.button("Process PDF"):
                # Process PDF
                with st.spinner("Processing PDF..."):
                    try:
                        processing_graph = create_processing_graph()
                        initial_state = {
                            "file_path": temp_path,
                            "messages": [],
                            "context": [],
                            "current_response": "",
                            "chunks": [],
                            "summaries": {},
                            "vector_db": st.session_state.vector_db,
                        }
                        processing_graph.invoke(initial_state)
                        st.session_state.processed_files.add(uploaded_file.name)
                        st.success("PDF processed successfully!")
                    except Exception as e:
                        st.error(f"Error processing PDF: {str(e)}")

    # Chat section
    user_question = st.text_input("Ask a question about any processed PDF:")

    if user_question:
        chat_graph = create_chat_graph()
        with st.spinner("Generating response..."):
            try:
                chat_state = {
                    "messages": [HumanMessage(content=user_question)],
                    "context": [],
                    "current_response": "",
                    "file_path": "",
                    "chunks": [],
                    "summaries": {},
                    "vector_db": st.session_state.vector_db,
                }
                result = chat_graph.invoke(chat_state)

                # Display the response
                st.subheader("Generated Response")
                if isinstance(result["current_response"], str):
                    st.write(result["current_response"])
                else:
                    st.write(result["current_response"]["response"])

                    # Display images if they exist in the context
                    if (
                        "context" in result["current_response"]
                        and result["current_response"]["context"]["images"]
                    ):
                        st.subheader("Related Images")
                        for img_url in result["current_response"]["context"]["images"]:
                            img_url = img_url.replace(
                                "http://minio:9000", "http://localhost:9200"
                            )
                            st.image(img_url)

            except Exception as e:
                st.error(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
