from __future__ import annotations

import base64
import io
import json
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter
from docling.document_converter import PdfFormatOption
from docling_core.types.doc import DocItemLabel
from docling_core.types.doc import PictureItem
from docling_core.types.doc import TableItem
from docling_core.types.doc import TextItem


def _label_value(label: object) -> str:
    if label is None:
        return ""
    if hasattr(label, "value"):
        return str(label.value)
    return str(label)


def _bbox_dict(prov) -> dict[str, float] | None:
    bbox = getattr(prov, "bbox", None)
    if bbox is None:
        return None
    return {
        "l": float(bbox.l),
        "t": float(bbox.t),
        "r": float(bbox.r),
        "b": float(bbox.b),
    }


def _text_preview(
    item: TextItem | TableItem | PictureItem,
    *,
    document,
    max_len: int = 200,
) -> str:
    if isinstance(item, TextItem):
        text = (item.text or "").strip()
    elif isinstance(item, TableItem):
        text = (item.export_to_markdown(doc=document) or "").strip()
    else:
        caption = getattr(item, "caption", None)
        text = str(caption).strip() if caption else ""

    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1].rstrip()}…"


def _element_from_item(
    item: TextItem | TableItem | PictureItem,
    *,
    document,
    default_label: str,
) -> dict[str, Any] | None:
    prov_list = getattr(item, "prov", None) or []
    if not prov_list:
        return None

    prov = prov_list[0]
    bbox = _bbox_dict(prov)
    page_no = getattr(prov, "page_no", None)
    if page_no is None or bbox is None:
        return None

    label = _label_value(getattr(item, "label", None)) or default_label
    ref = getattr(item, "self_ref", None)

    return {
        "id": str(ref) if ref else f"{default_label}-{page_no}",
        "label": label,
        "text": _text_preview(item, document=document),
        "page_no": int(page_no),
        "bbox": bbox,
    }


def _collect_elements(document) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []

    for item in document.texts:
        element = _element_from_item(
            item,
            document=document,
            default_label=DocItemLabel.TEXT.value,
        )
        if element is not None:
            elements.append(element)

    for item in document.tables:
        element = _element_from_item(item, document=document, default_label="table")
        if element is not None:
            elements.append(element)

    for item in document.pictures:
        element = _element_from_item(item, document=document, default_label="picture")
        if element is not None:
            elements.append(element)

    return elements


def _pil_to_jpeg_base64(pil_image) -> str:
    buffer = io.BytesIO()
    pil_image.save(buffer, format="JPEG", quality=80)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _page_image_base64(page_item) -> str | None:
    image_ref = getattr(page_item, "image", None)
    if image_ref is None:
        return None

    pil_image = getattr(image_ref, "pil_image", image_ref)
    if pil_image is None or not hasattr(pil_image, "save"):
        return None

    return _pil_to_jpeg_base64(pil_image)


def _build_pipeline_options() -> PdfPipelineOptions:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_page_images = True
    pipeline_options.images_scale = 1.0
    pipeline_options.do_table_structure = True
    pipeline_options.do_ocr = True
    pipeline_options.layout_batch_size = 1
    pipeline_options.ocr_batch_size = 1
    pipeline_options.table_batch_size = 1
    pipeline_options.queue_max_size = 4
    return pipeline_options


def extract_document_layout(file_path: str, *, filename: str = "") -> dict[str, Any]:
    """Parse a PDF with Docling and return a layout payload for the UI.

    Separate from ``pdf_processor.process_pdf`` — focused on page geometry and
    element bounding boxes rather than RAG chunking.
    """
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=_build_pipeline_options(),
            ),
        },
    )
    document = converter.convert(file_path).document

    elements_by_page: dict[int, list[dict[str, Any]]] = {}
    for element in _collect_elements(document):
        page_no = element.pop("page_no")
        elements_by_page.setdefault(page_no, []).append(element)

    pages: list[dict[str, Any]] = []
    for page_no in sorted(document.pages.keys()):
        page_item = document.pages[page_no]
        size = page_item.size
        pages.append(
            {
                "page_no": int(page_no),
                "width": float(size.width),
                "height": float(size.height),
                "elements": elements_by_page.get(int(page_no), []),
                "image_base64": _page_image_base64(page_item),
            },
        )

    return {
        "filename": filename,
        "page_count": len(pages),
        "pages": pages,
    }


def layout_to_json_bytes(layout: dict[str, Any]) -> bytes:
    return json.dumps(layout, ensure_ascii=False).encode("utf-8")
