"""
PDF Extraction Utility
Extracts and intelligently chunks text from uploaded PDF files.
"""
import io
import PyPDF2


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract full text from a PDF file given as bytes."""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                pages_text.append(text.strip())
        return "\n\n".join(pages_text)
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")


def chunk_text(text: str, max_chars: int = 8000) -> list[str]:
    """
    Split long text into chunks suitable for a single LLM prompt.
    Splits on double newlines first, then hard-cuts if needed.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 < max_chars:
            current += para + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            current = para + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks


def summarise_chunks(chunks: list[str], max_summary_chars: int = 10000) -> str:
    """
    Collapse chunks into one compressed summary string up to max_summary_chars.
    Used when the source is too large to send to LLM in a single prompt.
    """
    combined = "\n\n---\n\n".join(chunks)
    if len(combined) <= max_summary_chars:
        return combined
    # Hard truncate with a note
    return combined[:max_summary_chars] + "\n\n[...truncated for length...]"
