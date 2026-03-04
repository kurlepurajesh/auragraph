import io
import PyPDF2


def extract_text_from_pdf(file_bytes: bytes) -> str:
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


def chunk_text(text: str, max_chars: int = 8000) -> list:
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


def summarise_chunks(chunks: list, max_summary_chars: int = 10000) -> str:
    combined = "\n\n---\n\n".join(chunks)
    if len(combined) <= max_summary_chars:
        return combined
    return combined[:max_summary_chars] + "\n\n[...truncated for length...]"
