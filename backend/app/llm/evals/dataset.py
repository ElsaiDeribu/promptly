"""Persistence helpers for the golden eval dataset."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from langsmith import Client

from app.llm.evals.rag_eval import DEFAULT_DATASET_NAME
from app.llm.evals.rag_eval import langsmith_configured
from app.llm.evals.rag_eval import sync_dataset
from app.llm.models import Document
from app.llm.models import EvalExample


def load_golden_examples(*, document_id: int | None = None) -> list[dict[str, Any]]:
    """Load golden eval examples from Postgres."""
    queryset = EvalExample.objects.select_related("document").order_by("id")
    if document_id is not None:
        queryset = queryset.filter(document_id=document_id)

    return [
        {
            "inputs": example.inputs,
            "outputs": example.outputs,
        }
        for example in queryset
    ]


def replace_golden_examples_for_document(
    document: Document,
    examples: list[dict[str, Any]],
    *,
    sync_langsmith: bool = False,
) -> int:
    """Replace all golden examples for a document and optionally sync to LangSmith."""
    with transaction.atomic():
        EvalExample.objects.filter(document=document).delete()
        created = EvalExample.objects.bulk_create(
            [
                EvalExample(
                    document=document,
                    inputs=example["inputs"],
                    outputs=example.get("outputs", {}),
                )
                for example in examples
            ],
        )

        if sync_langsmith and langsmith_configured() and examples:
            transaction.on_commit(
                lambda: sync_dataset(Client(), DEFAULT_DATASET_NAME, examples),
            )

        return len(created)