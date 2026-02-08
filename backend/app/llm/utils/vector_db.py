from typing import Optional
import os
import boto3
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import Qdrant
from typing import List




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

