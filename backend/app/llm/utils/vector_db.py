import os

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import FastEmbedSparse
from langchain_qdrant import QdrantVectorStore
from langchain_qdrant import RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance
from qdrant_client.http.models import SparseIndexParams
from qdrant_client.http.models import SparseVectorParams
from qdrant_client.http.models import VectorParams
from sentence_transformers import CrossEncoder

DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker_cache: dict[str, CrossEncoder] = {}


def _get_reranker(model_name: str) -> CrossEncoder:
    if model_name not in _reranker_cache:
        _reranker_cache[model_name] = CrossEncoder(model_name)
    return _reranker_cache[model_name]


# ------------------------------------------------------------
# Vector Database
# ------------------------------------------------------------
class VectorDBWrapper:
    """Wrapper class for vector database operations to make it easy to swap implementations"""

    DENSE_VECTOR_NAME = "dense"
    SPARSE_VECTOR_NAME = "sparse"

    def __init__(
        self,
        embeddings: OpenAIEmbeddings | None = None,
        collection_name: str = "multi_modal_rag",
        enable_reranking: bool = True,
        rerank_model: str = DEFAULT_RERANK_MODEL,
        rerank_fetch_multiplier: int = 4,
    ):
        """Initialize the vector store wrapper

        Args:
            embeddings: Optional embeddings model, defaults to OpenAIEmbeddings if not provided
            collection_name: Name of the Qdrant collection to use
            enable_reranking: Whether to rerank vector search results with a cross-encoder
            rerank_model: sentence-transformers cross-encoder model for reranking
            rerank_fetch_multiplier: Fetch this many times k candidates before reranking
        """
        self.embeddings = embeddings if embeddings else OpenAIEmbeddings()
        self.collection_name = collection_name
        self.enable_reranking = enable_reranking
        self.rerank_model = rerank_model
        self.rerank_fetch_multiplier = rerank_fetch_multiplier

        # BM25 sparse embeddings, computed locally via fastembed
        self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

        # Get Qdrant connection details from environment
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", 6333))

        # Initialize Qdrant client
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)

        # Create collection if it doesn't exist
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            # Create new collection with both dense and sparse vector configs
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    self.DENSE_VECTOR_NAME: VectorParams(
                        size=1536, distance=Distance.COSINE
                    ),
                },
                sparse_vectors_config={
                    self.SPARSE_VECTOR_NAME: SparseVectorParams(
                        index=SparseIndexParams(on_disk=False)
                    ),
                },
            )

        # Initialize vectorstore in hybrid retrieval mode
        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name=self.DENSE_VECTOR_NAME,
            sparse_vector_name=self.SPARSE_VECTOR_NAME,
        )

    def add_documents(self, documents: list[Document]) -> None:
        """Add documents to vector store

        Args:
            documents: List of Documents to add
        """
        # Add to vectorstore
        self.vector_store.add_documents(documents)

    def _rerank_documents(
        self, query: str, documents: list[Document], k: int
    ) -> list[Document]:
        if not documents:
            return []

        reranker = _get_reranker(self.rerank_model)
        pairs = [(query, doc.page_content) for doc in documents]
        scores = reranker.predict(pairs)

        ranked = sorted(
            zip(scores, documents, strict=True),
            key=lambda item: item[0],
            reverse=True,
        )
        return [doc for _, doc in ranked[:k]]

    def similarity_search(self, query: str, k: int = 4) -> list[Document]:
        """Perform similarity search for a query

        Args:
            query: The search query
            k: Number of results to return

        Returns:
            List of relevant documents
        """
        fetch_k = k * self.rerank_fetch_multiplier if self.enable_reranking else k
        documents = self.vector_store.similarity_search(query, k=fetch_k)

        if self.enable_reranking:
            return self._rerank_documents(query, documents, k)

        return documents

    def scroll_by_document_id(self, document_id: int, *, limit: int = 256) -> list[Document]:
        """Return indexed chunks for a document via Qdrant metadata filter."""
        from qdrant_client.http.models import FieldCondition
        from qdrant_client.http.models import Filter
        from qdrant_client.http.models import MatchValue

        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.document_id",
                    match=MatchValue(value=document_id),
                ),
            ],
        )

        documents: list[Document] = []
        offset = None
        while len(documents) < limit:
            batch, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=scroll_filter,
                limit=min(64, limit - len(documents)),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not batch:
                break

            for point in batch:
                payload = point.payload or {}
                page_content = payload.get("page_content") or payload.get("text") or ""
                metadata = payload.get("metadata") or {}
                if not isinstance(metadata, dict):
                    metadata = {}
                documents.append(
                    Document(page_content=page_content, metadata=metadata),
                )

            if offset is None:
                break

        return documents
