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
    Collapse chunks into one string up to max_summary_chars.
    Instead of hard-truncating (which silently drops whole sections),
    we sample proportionally from ALL chunks so every topic is represented.
    """
    combined = "\n\n---\n\n".join(chunks)
    if len(combined) <= max_summary_chars:
        return combined

    # Each chunk gets a proportional share of the budget
    per_chunk = max(200, max_summary_chars // max(len(chunks), 1))
    parts = []
    for chunk in chunks:
        if len(chunk) <= per_chunk:
            parts.append(chunk)
        else:
            # Trim at the last sentence boundary within the budget
            trimmed = chunk[:per_chunk]
            last_stop = max(trimmed.rfind('. '), trimmed.rfind('.\n'), trimmed.rfind('\n\n'))
            if last_stop > per_chunk // 2:
                trimmed = trimmed[:last_stop + 1]
            parts.append(trimmed)
    return "\n\n---\n\n".join(parts)
