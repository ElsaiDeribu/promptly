import base64
from io import BytesIO

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.chunking import HybridChunker  # hierarchical + token-aware merging
from docling_core.types.doc import PictureItem, TableItem

# ------------------------------------------------------------
# Pre-processing
# ------------------------------------------------------------
def process_pdf(file_path: str, output_path: str = "./output/") -> list:
    """Process a PDF file and extract chunks with tables and images.
    Args:
        file_path: Path to the PDF file to process
        output_path: Directory to save extracted content (default: "./output/")
    Returns:
        List of chunk objects (docling BaseChunk) containing the extracted chunks,
        with chunk.meta.doc_items pointing back into the parsed DoclingDocument.
    """
    pipeline_options = PdfPipelineOptions(
        do_table_structure=True,          # equivalent to infer_table_structure=True
        generate_picture_images=True,     # needed so we can pull base64 images later
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(file_path)
    doc = result.document  # DoclingDocument — keep this around, chunks reference it

    # HybridChunker = hierarchical structure-aware chunking + token-aware splitting/merging
    # (closest equivalent to "by_title" but smarter about table/section boundaries)
    chunker = HybridChunker(max_tokens=10000)  # tune to mirror max_characters behavior
    chunks = list(chunker.chunk(doc))

    # stash the source doc on each chunk so get_images_base64/get_tables can use it
    for c in chunks:
        c._source_doc = doc

    return chunks

# ------------------------------------------------------------
# Utils
# ------------------------------------------------------------
# Get the images from the chunk's referenced doc items
def get_images_base64(chunks):
    images_b64 = []
    for chunk in chunks:
        doc = getattr(chunk, "_source_doc", None)
        if doc is None:
            continue
        for item in chunk.meta.doc_items:
            if isinstance(item, PictureItem):
                pil_img = item.get_image(doc)
                if pil_img is None:
                    continue
                buf = BytesIO()
                pil_img.save(buf, format="PNG")
                images_b64.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
    return images_b64

# Get the tables from the chunk's referenced doc items
def get_tables(chunks):
    tables = []
    for chunk in chunks:
        doc = getattr(chunk, "_source_doc", None)
        if doc is None:
            continue
        for item in chunk.meta.doc_items:
            if isinstance(item, TableItem):
                tables.append(item.export_to_markdown(doc))
    return tables