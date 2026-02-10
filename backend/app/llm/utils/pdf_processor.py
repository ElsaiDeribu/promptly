
from unstructured.documents.elements import Element
from unstructured.partition.pdf import partition_pdf


# ------------------------------------------------------------
# Pre-processing
# ------------------------------------------------------------
def process_pdf(file_path: str, output_path: str = "./output/") -> list[Element]:
    """Process a PDF file and extract chunks with tables and images.

    Args:
        file_path: Path to the PDF file to process
        output_path: Directory to save extracted content (default: "./output/")

    Returns:
        List of document elements containing the extracted chunks
    """
    # Reference: https://docs.unstructured.io/open-source/core-functionality/chunking
    chunks = partition_pdf(
        filename=file_path,
        infer_table_structure=True,  # extract tables
        strategy="hi_res",  # mandatory to infer tables
        extract_image_block_types=[
            "Image",
        ],  # Add 'Table' to list to extract image of tables
        # image_output_dir_path=output_path,   # if None, images and tables will saved in base64
        extract_image_block_to_payload=True,  # if true, will extract base64 for API usage
        chunking_strategy="by_title",  # or 'basic'
        max_characters=10000,  # defaults to 500
        combine_text_under_n_chars=2000,  # defaults to 0
        new_after_n_chars=6000,
        # extract_images_in_pdf=True,          # deprecated
    )

    return chunks




# ------------------------------------------------------------
# Utils
# ------------------------------------------------------------
# Get the images from the CompositeElement objects
def get_images_base64(chunks):
    images_b64 = []
    for chunk in chunks:
        if "CompositeElement" in str(type(chunk)):
            chunk_els = chunk.metadata.orig_elements
            for el in chunk_els:
                if "Image" in str(type(el)):
                    images_b64.append(el.metadata.image_base64)
    return images_b64


# Get the tables from the CompositeElement objects
def get_tables(chunks):
    tables = []
    for chunk in chunks:
        if "CompositeElement" in str(type(chunk)):
            chunk_els = chunk.metadata.orig_elements
            for el in chunk_els:
                if "Table" in str(type(el)):
                    tables.append(el.text)
    return tables

