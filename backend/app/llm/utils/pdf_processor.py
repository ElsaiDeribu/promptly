from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any

import tiktoken
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.pipeline_options import TableFormerMode
from docling.datamodel.pipeline_options import TableStructureOptions
from docling.document_converter import DocumentConverter
from docling.document_converter import PdfFormatOption
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc import DocItemLabel
from docling_core.types.doc import PictureItem
from docling_core.types.doc import TableItem

# Align chunk size with OpenAI embedding models (cl100k_base, 8191-token context).
CHUNK_MAX_TOKENS = 512
MIN_IMAGE_WIDTH = 100
MIN_IMAGE_HEIGHT = 100


@dataclass
class ProcessedChunk:
    """A structure-aware document chunk with provenance metadata."""

    text: str
    content_type: str
    provenance: dict[str, Any] = field(default_factory=dict)
    image_bytes: bytes | None = None


def _label_value(label: object) -> str:
    if label is None:
        return ""
    if hasattr(label, "value"):
        return str(label.value)
    return str(label)


def _content_type_for_chunk(chunk) -> str:
    for item in chunk.meta.doc_items:
        label = getattr(item, "label", None)
        if label == DocItemLabel.PICTURE:
            return "image"
        if label == DocItemLabel.TABLE:
            return "table"
    labels = {_label_value(getattr(item, "label", None)) for item in chunk.meta.doc_items}
    labels.discard("")
    if "picture" in labels:
        return "image"
    if "table" in labels:
        return "table"
    return "text"


def _bbox_from_prov(prov) -> dict[str, float | int] | None:
    bbox = getattr(prov, "bbox", None)
    if bbox is None:
        return None
    return {
        "page_no": prov.page_no,
        "l": float(bbox.l),
        "t": float(bbox.t),
        "r": float(bbox.r),
        "b": float(bbox.b),
    }


def _provenance_from_item(item: PictureItem | TableItem, element_label: str) -> dict[str, Any]:
    provenance: dict[str, Any] = {"element_label": element_label}
    ref = getattr(item, "self_ref", None)
    if ref:
        provenance["doc_item_ref"] = str(ref)

    for prov in getattr(item, "prov", None) or []:
        page_no = getattr(prov, "page_no", None)
        if page_no is not None:
            provenance["page_no"] = int(page_no)
        bbox = _bbox_from_prov(prov)
        if bbox is not None:
            provenance["bbox"] = json.dumps(bbox)
        break

    return provenance


def _extract_provenance(chunk) -> dict[str, Any]:
    """Map Docling chunk metadata to flat Qdrant-friendly provenance fields."""
    meta = chunk.meta
    provenance: dict[str, Any] = {}

    headings = list(getattr(meta, "headings", None) or [])
    if headings:
        provenance["headings"] = headings

    captions = list(getattr(meta, "captions", None) or [])
    if captions:
        provenance["captions"] = captions

    page_numbers: list[int] = []
    doc_item_refs: list[str] = []
    element_labels: list[str] = []
    bboxes: list[dict[str, float | int]] = []

    for item in chunk.meta.doc_items:
        label = _label_value(getattr(item, "label", None))
        if label:
            element_labels.append(label)

        ref = getattr(item, "self_ref", None)
        if ref:
            doc_item_refs.append(str(ref))

        for prov in getattr(item, "prov", None) or []:
            page_no = getattr(prov, "page_no", None)
            if page_no is not None:
                page_numbers.append(int(page_no))
            bbox = _bbox_from_prov(prov)
            if bbox is not None:
                bboxes.append(bbox)

    if page_numbers:
        provenance["page_no"] = page_numbers[0]

    if element_labels:
        provenance["element_label"] = (
            element_labels[0] if len(element_labels) == 1 else element_labels
        )

    if doc_item_refs:
        provenance["doc_item_ref"] = (
            doc_item_refs[0] if len(doc_item_refs) == 1 else doc_item_refs
        )

    if bboxes:
        provenance["bbox"] = json.dumps(bboxes[0])

    return provenance


def _is_usable_text(text: str) -> bool:
    """Reject short OCR noise that would pollute the vector store."""
    text = text.strip()
    if len(text) < 15:
        return False

    words = re.findall(r"[A-Za-z]{3,}", text)
    if len(words) < 2:
        return False

    readable = sum(1 for char in text if char.isalnum() or char.isspace())
    return readable / len(text) >= 0.65


def _pil_to_jpeg_bytes(pil_image) -> bytes:
    buffer = io.BytesIO()
    pil_image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _picture_chunks(document) -> list[ProcessedChunk]:
    chunks: list[ProcessedChunk] = []
    for picture in document.pictures:
        pil_image = picture.get_image(document)
        if pil_image is None:
            continue
        if pil_image.width < MIN_IMAGE_WIDTH or pil_image.height < MIN_IMAGE_HEIGHT:
            continue

        caption = getattr(picture, "caption", None)
        text = str(caption).strip() if caption else ""

        chunks.append(
            ProcessedChunk(
                text=text,
                content_type="image",
                provenance=_provenance_from_item(picture, "picture"),
                image_bytes=_pil_to_jpeg_bytes(pil_image),
            ),
        )
    return chunks


def _table_chunks(document) -> list[ProcessedChunk]:
    chunks: list[ProcessedChunk] = []
    for table in document.tables:
        text = (table.export_to_markdown(doc=document) or "").strip()
        if not text:
            continue
        chunks.append(
            ProcessedChunk(
                text=text,
                content_type="table",
                provenance=_provenance_from_item(table, "table"),
            ),
        )
    return chunks


def _build_chunker() -> HybridChunker:
    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.get_encoding("cl100k_base"),
        max_tokens=CHUNK_MAX_TOKENS,
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


def _build_pipeline_options() -> PdfPipelineOptions:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode.ACCURATE,
    )
    # Smart OCR: do_ocr enables OCR for scanned pages; digital PDFs skip OCR automatically.
    pipeline_options.do_ocr = True
    pipeline_options.layout_batch_size = 1
    pipeline_options.ocr_batch_size = 1
    pipeline_options.table_batch_size = 1
    pipeline_options.queue_max_size = 4
    return pipeline_options


def _append_unique(
    processed: list[ProcessedChunk],
    chunk: ProcessedChunk,
    seen_refs: set[str],
) -> None:
    doc_item_ref = chunk.provenance.get("doc_item_ref")
    if doc_item_ref and str(doc_item_ref) in seen_refs:
        return
    processed.append(chunk)
    if doc_item_ref:
        seen_refs.add(str(doc_item_ref))


def process_pdf(file_path: str) -> list[ProcessedChunk]:
    """Parse a PDF with Docling and return hybrid-chunked elements with provenance."""
    # Reference: https://docling-project.github.io/docling/concepts/chunking/
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=_build_pipeline_options(),
            ),
        },
    )
    document = converter.convert(file_path).document
    chunker = _build_chunker()

    processed: list[ProcessedChunk] = []
    seen_refs: set[str] = set()

    for chunk in chunker.chunk(dl_doc=document):
        content_type = _content_type_for_chunk(chunk)
        if content_type == "image":
            continue

        text = (chunk.text or "").strip()
        if not text:
            continue
        if content_type == "text" and not _is_usable_text(text):
            continue

        _append_unique(
            processed,
            ProcessedChunk(
                text=text,
                content_type=content_type,
                provenance=_extract_provenance(chunk),
            ),
            seen_refs,
        )

    for chunk in _table_chunks(document):
        _append_unique(processed, chunk, seen_refs)

    for chunk in _picture_chunks(document):
        _append_unique(processed, chunk, seen_refs)

    return processed
