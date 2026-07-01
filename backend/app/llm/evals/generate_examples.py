"""Generate golden eval Q/A pairs for a processed document."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.llm.models import Document
from app.llm.services.multimodal_rag.rag_pipeline import create_processing_state
from app.llm.services.multimodal_rag.rag_pipeline import describe_image_chunks
from app.llm.services.multimodal_rag.rag_pipeline import pre_process_pdf
from app.llm.utils.s3 import S3Wrapper
from app.llm.utils.vector_db import VectorDBWrapper

logger = logging.getLogger(__name__)

MAX_PASSAGES = 15
MAX_QUESTIONS_PER_PASSAGE = 2
MAX_PASSAGE_CHARS = 2000

QA_PROMPT = ChatPromptTemplate.from_template(
    """
You generate evaluation question-answer pairs for a RAG system.
Given a passage from a document, write up to {max_pairs} questions that can be
answered strictly from the passage. Keep answers concise and factual.

Document filename: {filename}

Passage:
{passage}

Respond with JSON only in this shape:
{{"pairs": [{{"question": "...", "answer": "..."}}]}}
""",
)


def _dedupe_passages(documents: list) -> list[dict[str, Any]]:
    """Prefer one passage per source_id; keep the shorter summary when duplicated."""
    by_source: dict[str, dict[str, Any]] = {}
    for doc in documents:
        metadata = doc.metadata or {}
        source_id = str(metadata.get("source_id") or doc.page_content[:80])
        content = (doc.page_content or "").strip()
        if not content:
            continue

        existing = by_source.get(source_id)
        if existing is None or len(content) < len(existing["content"]):
            by_source[source_id] = {
                "source_id": source_id,
                "content": content[:MAX_PASSAGE_CHARS],
                "content_type": metadata.get("content_type", "text"),
            }

    return list(by_source.values())[:MAX_PASSAGES]


def _passages_from_vector_store(document: Document) -> list[dict[str, Any]]:
    vector_db = VectorDBWrapper()
    docs = vector_db.scroll_by_document_id(document.id)
    return _dedupe_passages(docs)


def _passages_from_pdf_resummarize(document: Document) -> list[dict[str, Any]]:
    """Fallback when vectors were indexed before document_id metadata existed."""
    s3 = S3Wrapper()
    data = s3.get_file(document.s3_key)
    if data is None:
        msg = f"Object {document.s3_key} not found in S3"
        raise FileNotFoundError(msg)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf",
            prefix="eval_gen_",
        ) as tmp_file:
            tmp_file.write(data)
            temp_path = tmp_file.name

        state = create_processing_state(
            temp_path,
            document_id=document.id,
            original_filename=document.original_filename,
        )
        state = pre_process_pdf(state)
        image_chunks = [
            c for c in state["chunks"]
            if c.content_type == "image" and c.image_bytes
        ]
        image_summaries = describe_image_chunks(image_chunks)

        passages: list[dict[str, Any]] = []
        for index, chunk in enumerate(state["chunks"]):
            if chunk.content_type in ("text", "table") and chunk.text.strip():
                passages.append(
                    {
                        "source_id": f"{chunk.content_type}-{index}",
                        "content": chunk.text.strip()[:MAX_PASSAGE_CHARS],
                        "content_type": chunk.content_type,
                    },
                )
        for index, summary in enumerate(image_summaries):
            if not summary or not summary.strip():
                continue
            passages.append(
                {
                    "source_id": f"image-{index}",
                    "content": summary.strip()[:MAX_PASSAGE_CHARS],
                    "content_type": "image",
                },
            )
        return passages[:MAX_PASSAGES]
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def fetch_passages_for_document(document: Document) -> list[dict[str, Any]]:
    passages = _passages_from_vector_store(document)
    if passages:
        return passages

    logger.info(
        "No indexed passages found for document %s; re-summarizing PDF from S3",
        document.id,
    )
    return _passages_from_pdf_resummarize(document)


def _parse_qa_response(raw: str) -> list[dict[str, str]]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    payload = json.loads(cleaned)
    pairs = payload.get("pairs", [])
    results: list[dict[str, str]] = []
    for pair in pairs[:MAX_QUESTIONS_PER_PASSAGE]:
        question = (pair.get("question") or "").strip()
        answer = (pair.get("answer") or "").strip()
        if question and answer:
            results.append({"question": question, "answer": answer})
    return results


def _generate_pairs_for_passage(
    passage: dict[str, Any],
    *,
    filename: str,
    model: ChatOpenAI,
) -> list[dict[str, str]]:
    chain = QA_PROMPT | model | StrOutputParser()
    raw = chain.invoke(
        {
            "filename": filename,
            "passage": passage["content"],
            "max_pairs": MAX_QUESTIONS_PER_PASSAGE,
        },
    )
    return _parse_qa_response(raw)


def generate_golden_examples_for_document(document: Document) -> list[dict[str, Any]]:
    """Build golden eval examples for one document."""
    passages = fetch_passages_for_document(document)
    if not passages:
        msg = f"No content available to generate eval examples for document {document.id}"
        raise ValueError(msg)

    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    examples: list[dict[str, Any]] = []
    seen_questions: set[str] = set()

    for passage in passages:
        try:
            pairs = _generate_pairs_for_passage(
                passage,
                filename=document.original_filename,
                model=model,
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.exception(
                "Failed to parse generated Q/A for document %s passage %s",
                document.id,
                passage.get("source_id"),
            )
            continue

        for pair in pairs:
            normalized = pair["question"].strip().lower()
            if normalized in seen_questions:
                continue
            seen_questions.add(normalized)

            examples.append(
                {
                    "inputs": {
                        "question": pair["question"],
                        "document_id": document.id,
                    },
                    "outputs": {
                        "answer": pair["answer"],
                        "source_ids": [passage["source_id"]],
                        "document_filename": document.original_filename,
                        "content_type": passage.get("content_type", "text"),
                    },
                },
            )

    if not examples:
        msg = f"LLM did not produce any valid eval examples for document {document.id}"
        raise ValueError(msg)

    return examples
