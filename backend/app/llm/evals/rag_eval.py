"""LangSmith offline evaluation for the multimodal RAG chat pipeline."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from langsmith import Client
from langsmith import evaluate
from langsmith import traceable
from langsmith.schemas import Example

from app.llm.services.multimodal_rag.rag_pipeline import run_rag_query

SAMPLE_DATASET_PATH = Path(__file__).parent / "sample_dataset.json"
DEFAULT_DATASET_NAME = "promptly-multimodal-rag"


@traceable(name="rag_eval_target")
def rag_eval_target(inputs: dict[str, Any]) -> dict[str, Any]:
    return run_rag_query(inputs["question"])


def has_retrieved_context(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any] | None,
) -> dict[str, Any]:
    context = outputs.get("context") or {}
    has_context = bool(context.get("texts") or context.get("images"))
    return {"key": "has_context", "score": 1.0 if has_context else 0.0}


def answer_not_empty(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any] | None,
) -> dict[str, Any]:
    answer = (outputs.get("answer") or "").strip().lower()
    if not answer or "don't have enough context" in answer:
        return {"key": "answer_not_empty", "score": 0.0}
    return {"key": "answer_not_empty", "score": 1.0}


def reference_answer_overlap(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any] | None,
) -> dict[str, Any]:
    reference = ((reference_outputs or {}).get("answer") or "").strip()
    if not reference:
        return {"key": "reference_overlap", "score": None}

    answer_words = set((outputs.get("answer") or "").lower().split())
    reference_words = set(reference.lower().split())
    if not reference_words:
        return {"key": "reference_overlap", "score": None}

    overlap = len(answer_words & reference_words) / len(reference_words)
    return {"key": "reference_overlap", "score": overlap}


DEFAULT_EVALUATORS = [
    has_retrieved_context,
    answer_not_empty,
    reference_answer_overlap,
]


def load_examples(dataset_path: Path | None = None) -> list[dict[str, Any]]:
    path = dataset_path or SAMPLE_DATASET_PATH
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def dicts_to_examples(raw: list[dict[str, Any]]) -> list[Example]:
    now = datetime.now(tz=timezone.utc)
    ds_id = uuid.uuid4()
    return [
        Example(
            id=uuid.uuid4(),
            inputs=ex["inputs"],
            outputs=ex.get("outputs", {}),
            dataset_id=ds_id,
            created_at=now,
            modified_at=now,
        )
        for ex in raw
    ]


def langsmith_configured() -> bool:
    return bool(os.getenv("LANGSMITH_API_KEY"))


def sync_dataset(
    client: Client,
    dataset_name: str,
    examples: list[dict[str, Any]],
) -> str:
    try:
        dataset = client.read_dataset(dataset_name=dataset_name)
    except Exception:
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Promptly multimodal RAG evaluation examples",
        )

    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {
                "inputs": example["inputs"],
                "outputs": example.get("outputs", {}),
            }
            for example in examples
        ],
    )
    return dataset_name


def run_rag_evaluation(
    *,
    examples: list[dict[str, Any]] | None = None,
    dataset_name: str = DEFAULT_DATASET_NAME,
    experiment_prefix: str = "promptly-rag",
    upload_results: bool = True,
    sync_to_langsmith: bool = False,
    max_concurrency: int = 1,
) -> Any:
    """Run offline evals against the RAG chat pipeline."""
    loaded_examples = examples or load_examples()

    if upload_results and not langsmith_configured():
        msg = "LANGSMITH_API_KEY is required when uploading eval results."
        raise RuntimeError(msg)

    data: str | list[Example] = dicts_to_examples(loaded_examples)
    if sync_to_langsmith:
        client = Client()
        data = sync_dataset(client, dataset_name, loaded_examples)

    return evaluate(
        rag_eval_target,
        data=data,
        evaluators=DEFAULT_EVALUATORS,
        experiment_prefix=experiment_prefix,
        max_concurrency=max_concurrency,
        upload_results=upload_results,
        metadata={"pipeline": "multimodal_rag"},
    )
