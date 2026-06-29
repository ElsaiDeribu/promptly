"""LangSmith offline evaluation for the multimodal RAG chat pipeline."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI
from langsmith import Client
from langsmith import evaluate
from langsmith import traceable
from langsmith.schemas import Example
from langsmith.utils import LangSmithNotFoundError
from pydantic import BaseModel
from pydantic import Field

from app.llm.agents.rag_agent import build_rag_agent

SAMPLE_DATASET_PATH = Path(__file__).parent / "sample_dataset.json"
DEFAULT_DATASET_NAME = "promptly-multimodal-rag"
MAX_CONTEXT_CHARS = 12_000


@traceable(name="rag_eval_target")
def rag_eval_target(inputs: dict[str, Any]) -> dict[str, Any]:
    document_id = inputs.get("document_id")
    agent = build_rag_agent(user_id="eval", document_id=document_id)
    result = agent.invoke(
        {"messages": [HumanMessage(content=inputs["question"])]},
        config={"run_name": "rag_agent_query"},
    )
    messages = result.get("messages", [])
    return {"answer": messages[-1].content if messages else "", "messages": messages}


class EvalGrade(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reason: str


_JUDGE = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
).with_structured_output(EvalGrade)

_FAITHFULNESS_PROMPT = """You judge whether an answer is faithful to (grounded in) the retrieved context.

Rules:
- 1.0: every factual claim in the answer is supported by the context
- 0.0: the answer invents facts or contradicts the context
- If the answer correctly says it lacks enough information and the context is empty or irrelevant, score 1.0
- Ignore style; only judge factual grounding

Question:
{question}

Retrieved context:
{context}

Answer:
{answer}
"""

_RELEVANCY_PROMPT = """You judge whether an answer is relevant to the question asked.

Rules:
- 1.0: the answer directly and fully addresses the question
- 0.0: the answer is off-topic, evasive without cause, or does not address the question
- Partial scores for partially relevant answers
- Do not judge factual grounding in source documents (that is scored separately)

Question:
{question}

Answer:
{answer}
"""


def _extract_retrieved_context(messages: list[BaseMessage]) -> str:
    chunks: list[str] = []
    for message in messages:
        if (
            isinstance(message, ToolMessage)
            and message.name == "vector_rag_tool"
            and "No relevant context found" not in message.content
        ):
            chunks.append(message.content)
    context = "\n\n".join(chunks)
    if len(context) > MAX_CONTEXT_CHARS:
        return context[:MAX_CONTEXT_CHARS]
    return context


def faithfulness(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    """LLM-as-judge: score how grounded the answer is in retrieved context."""
    context = _extract_retrieved_context(outputs.get("messages") or [])
    answer = (outputs.get("answer") or "").strip()

    if not context:
        return {
            "key": "faithfulness",
            "score": None,
            "comment": "No retrieved context to judge against.",
        }
    if not answer:
        return {"key": "faithfulness", "score": 0.0, "comment": "Empty answer."}

    grade = _JUDGE.invoke(
        _FAITHFULNESS_PROMPT.format(
            question=inputs["question"],
            context=context,
            answer=answer,
        ),
    )
    return {
        "key": "faithfulness",
        "score": grade.score,
        "comment": grade.reason,
    }


def answer_relevancy(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    """LLM-as-judge: score how relevant the answer is to the question."""
    answer = (outputs.get("answer") or "").strip()
    if not answer:
        return {"key": "answer_relevancy", "score": 0.0, "comment": "Empty answer."}

    grade = _JUDGE.invoke(
        _RELEVANCY_PROMPT.format(
            question=inputs["question"],
            answer=answer,
        ),
    )
    return {
        "key": "answer_relevancy",
        "score": grade.score,
        "comment": grade.reason,
    }


DEFAULT_EVALUATORS = [faithfulness, answer_relevancy]


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
    except LangSmithNotFoundError:
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
    if examples is None:
        from app.llm.evals.dataset import load_golden_examples

        loaded_examples = load_golden_examples()
    else:
        loaded_examples = examples

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
