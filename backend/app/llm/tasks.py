import json
import logging
import os
import tempfile

from celery import shared_task

from .models import Document
from .services.document_layout.layout_extractor import extract_document_layout
from .services.document_layout.layout_extractor import layout_to_json_bytes
from .services.multimodal_rag.rag_pipeline import create_processing_graph
from .services.multimodal_rag.rag_pipeline import create_processing_state
from .utils.s3 import S3Wrapper

logger = logging.getLogger(__name__)


# This task needs more time than Celery's default limits due to slow PDF parsing and LLM summarization.
PROCESS_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
PROCESS_HARD_TIME_LIMIT = 30 * 60  # 30 minutes


@shared_task(
    bind=True,
    max_retries=3,
    soft_time_limit=PROCESS_SOFT_TIME_LIMIT,
    time_limit=PROCESS_HARD_TIME_LIMIT,
)
def process_document(self, document_id: int):
    """Asynchronously processes a document from S3.

    Downloads the document from S3, stores it temporarily on disk,
    and executes the multimodal RAG processing pipeline.
    """
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("process_document: document %s not found", document_id)
        return

    document.status = Document.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message", "updated_at"])

    temp_path = None
    try:
        s3 = S3Wrapper()
        data = s3.get_file(document.s3_key)
        if data is None:
            msg = f"Object {document.s3_key} not found in S3"
            raise FileNotFoundError(msg)

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".pdf", prefix="rag_",
        ) as tmp_file:
            tmp_file.write(data)
            temp_path = tmp_file.name

        processing_graph = create_processing_graph()
        initial_state = create_processing_state(
            temp_path,
            document_id=document.id,
            original_filename=document.original_filename,
        )
        processing_graph.invoke(initial_state)

        document.status = Document.Status.PROCESSED
        document.save(update_fields=["status", "updated_at"])
    except Exception as exc:
        logger.exception("Failed to process document %s", document_id)
        document.status = Document.Status.FAILED
        document.error_message = str(exc)
        document.save(update_fields=["status", "error_message", "updated_at"])
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


GENERATE_EVAL_SOFT_TIME_LIMIT = 20 * 60
GENERATE_EVAL_HARD_TIME_LIMIT = 25 * 60


@shared_task(
    bind=True,
    max_retries=1,
    soft_time_limit=GENERATE_EVAL_SOFT_TIME_LIMIT,
    time_limit=GENERATE_EVAL_HARD_TIME_LIMIT,
)
def generate_eval_examples(self, document_id: int, sync_langsmith: bool = False):
    """Generate golden eval examples for a processed document."""
    from .evals.dataset import replace_golden_examples_for_document
    from .evals.generate_examples import generate_golden_examples_for_document

    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("generate_eval_examples: document %s not found", document_id)
        return

    try:
        examples = generate_golden_examples_for_document(document)
        count = replace_golden_examples_for_document(
            document,
            examples,
            sync_langsmith=sync_langsmith,
        )
        document.eval_generation_status = "completed"
        document.save(update_fields=["eval_generation_status", "updated_at"])
        logger.info(
            "Generated %s eval examples for document %s",
            count,
            document_id,
        )
        return {"document_id": document_id, "examples_added": count}
    except Exception:
        logger.exception("Failed to generate eval examples for document %s", document_id)
        document.eval_generation_status = "failed"
        document.save(update_fields=["eval_generation_status", "updated_at"])
        raise


LAYOUT_SOFT_TIME_LIMIT = 20 * 60
LAYOUT_HARD_TIME_LIMIT = 25 * 60


@shared_task(
    bind=True,
    max_retries=1,
    soft_time_limit=LAYOUT_SOFT_TIME_LIMIT,
    time_limit=LAYOUT_HARD_TIME_LIMIT,
)
def extract_document_layout_task(self, document_id: int):
    """Extract and store Docling layout JSON for a document."""
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("extract_document_layout_task: document %s not found", document_id)
        return

    temp_path = None
    try:
        s3 = S3Wrapper()
        data = s3.get_file(document.s3_key)
        if data is None:
            msg = f"Object {document.s3_key} not found in S3"
            raise FileNotFoundError(msg)

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".pdf", prefix="layout_",
        ) as tmp_file:
            tmp_file.write(data)
            temp_path = tmp_file.name

        layout = extract_document_layout(
            temp_path,
            filename=document.original_filename,
        )
        layout_key = f"layouts/{document.id}/layout.json"
        uploaded = s3.put_file(
            layout_to_json_bytes(layout),
            layout_key,
            content_type="application/json",
        )
        if not uploaded:
            msg = f"Failed to upload layout to {layout_key}"
            raise RuntimeError(msg)

        document.layout_generation_status = "completed"
        document.layout_s3_key = layout_key
        document.layout_error_message = ""
        document.save(
            update_fields=[
                "layout_generation_status",
                "layout_s3_key",
                "layout_error_message",
                "updated_at",
            ],
        )
        logger.info("Stored layout for document %s at %s", document_id, layout_key)
        return {"document_id": document_id, "layout_s3_key": layout_key}
    except Exception as exc:
        logger.exception("Failed to extract layout for document %s", document_id)
        document.layout_generation_status = "failed"
        document.layout_error_message = str(exc)
        document.save(
            update_fields=[
                "layout_generation_status",
                "layout_error_message",
                "updated_at",
            ],
        )
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


OUTLINE_SOFT_TIME_LIMIT = 10 * 60
OUTLINE_HARD_TIME_LIMIT = 15 * 60


@shared_task(
    bind=True,
    max_retries=1,
    soft_time_limit=OUTLINE_SOFT_TIME_LIMIT,
    time_limit=OUTLINE_HARD_TIME_LIMIT,
)
def generate_study_outline_task(
    self,
    document_id: int,
    *,
    revision_instruction: str = "",
):
    """Generate or revise a study outline from the document layout."""
    from .services.study_outline.outline_generator import generate_study_outline
    from .services.study_outline.outline_generator import outline_to_json_bytes
    from .services.study_outline.outline_generator import revise_study_outline

    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.error("generate_study_outline_task: document %s not found", document_id)
        return

    try:
        s3 = S3Wrapper()
        if not document.layout_s3_key:
            msg = "Layout must be extracted before generating study outline"
            raise ValueError(msg)

        raw_layout = s3.get_file(document.layout_s3_key)
        if raw_layout is None:
            msg = f"Layout {document.layout_s3_key} not found in S3"
            raise FileNotFoundError(msg)

        layout = json.loads(raw_layout.decode("utf-8"))

        if revision_instruction:
            if not document.outline_s3_key:
                msg = "No existing outline to revise"
                raise ValueError(msg)
            raw_outline = s3.get_file(document.outline_s3_key)
            if raw_outline is None:
                msg = f"Outline {document.outline_s3_key} not found in S3"
                raise FileNotFoundError(msg)
            current_outline = json.loads(raw_outline.decode("utf-8"))
            outline = revise_study_outline(
                current_outline,
                filename=document.original_filename,
                instruction=revision_instruction,
            )
        else:
            outline = generate_study_outline(
                layout,
                filename=document.original_filename,
            )

        outline_key = f"outlines/{document.id}/outline.json"
        uploaded = s3.put_file(
            outline_to_json_bytes(outline),
            outline_key,
            content_type="application/json",
        )
        if not uploaded:
            msg = f"Failed to upload outline to {outline_key}"
            raise RuntimeError(msg)

        document.outline_generation_status = "completed"
        document.outline_s3_key = outline_key
        document.outline_error_message = ""
        document.save(
            update_fields=[
                "outline_generation_status",
                "outline_s3_key",
                "outline_error_message",
                "updated_at",
            ],
        )
        logger.info("Stored study outline for document %s at %s", document_id, outline_key)
        return {"document_id": document_id, "outline_s3_key": outline_key}
    except Exception as exc:
        logger.exception("Failed to generate study outline for document %s", document_id)
        document.outline_generation_status = "failed"
        document.outline_error_message = str(exc)
        document.save(
            update_fields=[
                "outline_generation_status",
                "outline_error_message",
                "updated_at",
            ],
        )
        raise
