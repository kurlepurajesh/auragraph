"""
backend/agents/image_ocr.py
────────────────────────────
Extracts text from handwritten or printed notes images.

Supported formats: JPEG, PNG, WebP, BMP, TIFF, HEIC/HEIF

Strategy (in order):
  1. Groq vision  (llama-3.2-11b-vision-preview)  — best for handwriting
  2. pytesseract + Pillow                          — printed text fallback
  3. Descriptive placeholder                       — last resort

The output is formatted with --- Page: <name> --- markers so the rest of
the pipeline treats each image exactly like a slide page.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Supported image extensions ────────────────────────────────────────────────

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg',
    '.png',
    '.webp',
    '.bmp',
    '.tiff', '.tif',
    '.heic', '.heif',
}

_MIME_MAP = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.tiff': 'image/tiff', '.tif': 'image/tiff',
    '.heic': 'image/heic', '.heif': 'image/heif',
}

# ── Prompts ───────────────────────────────────────────────────────────────────

_OCR_SYSTEM = """\
You are a precise academic transcription assistant.
Your only job is to faithfully extract every piece of text from an image of
lecture notes — handwritten or printed — without omitting anything.
"""

_OCR_PROMPT = """\
The image contains lecture notes (handwritten, printed, or mixed).

Transcribe ALL visible text EXACTLY as written. Follow these rules:

CONTENT TO INCLUDE:
• Every heading and subheading (preserve hierarchy)
• All bullet points and numbered lists
• Mathematical formulas → convert to LaTeX inline ($...$) or display ($$...$$)
  e.g. "x squared" → $x^2$, "integral from 0 to T" → $\\int_0^T$
• Arrows, labels, and annotations on diagrams
• Tables → reproduce as a Markdown pipe-table
• Anything circled, underlined, or starred (mark with ** emphasis **)

DIAGRAMS:
• If there is a diagram/figure, add: [Diagram: one-line description of what it shows]

FORMAT RULES:
• Start directly with the text — no preamble like "Here is the transcription"
• Use blank lines between sections
• Preserve indentation hierarchy with bullets (•, -) or numbers

Do NOT skip, paraphrase, or summarise anything.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_image_file(filename: str) -> bool:
    """Return True if the filename has an image extension we can process."""
    return Path(filename.lower()).suffix in IMAGE_EXTENSIONS


def _guess_mime(filename: str) -> str:
    return _MIME_MAP.get(Path(filename.lower()).suffix, 'image/jpeg')


def _convert_heic(image_bytes: bytes) -> tuple[bytes, str]:
    """Convert HEIC/HEIF → JPEG using pillow-heif (if installed)."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=95)
        return buf.getvalue(), 'image/jpeg'
    except Exception as e:
        logger.debug("HEIC conversion failed (%s) — passing raw bytes to Groq", e)
        return image_bytes, 'image/heic'


def _format_section(text: str, filename: str) -> str:
    """Wrap extracted text with a page marker for downstream pipeline."""
    name = Path(filename).stem
    return f"--- Page: {name} ---\n{text.strip()}\n"


# ── Groq vision OCR ───────────────────────────────────────────────────────────

def _ocr_with_groq(image_bytes: bytes, filename: str) -> str:
    """
    Call Groq llama-3.2-11b-vision-preview to read notes from an image.
    Returns extracted text string, or '' on failure / no key.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        logger.debug("image_ocr: GROQ_API_KEY not set — skipping vision OCR")
        return ""

    # HEIC needs conversion first
    fname_lower = filename.lower()
    if fname_lower.endswith(('.heic', '.heif')):
        image_bytes, mime = _convert_heic(image_bytes)
    else:
        mime = _guess_mime(filename)

    b64 = base64.b64encode(image_bytes).decode()

    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
        model = os.environ.get("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")
        logger.info("image_ocr: calling Groq vision (%s) for %s", model, filename)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _OCR_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _OCR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=4096,
            temperature=0.1,   # faithful transcription, near-zero creativity
        )
        result = resp.choices[0].message.content.strip()
        logger.info("image_ocr: Groq extracted %d chars from %s", len(result), filename)
        return result
    except Exception as e:
        logger.warning("image_ocr: Groq vision failed for %s: %s", filename, e)
        return ""


# ── pytesseract OCR (printed text fallback) ───────────────────────────────────

def _ocr_with_tesseract(image_bytes: bytes, filename: str) -> str:
    """
    Local OCR using pytesseract + Pillow.
    Works well for printed text; mediocre for handwriting.
    """
    try:
        import pytesseract
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes))
        # Upscale small images — tesseract works better at 300+ DPI equivalent
        w, h = img.size
        if max(w, h) < 1200:
            scale = 1200 / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        text = pytesseract.image_to_string(img, config='--psm 6 --oem 3')
        text = text.strip()
        if text:
            logger.info("image_ocr: tesseract extracted %d chars from %s", len(text), filename)
        return text
    except ImportError:
        logger.debug("pytesseract not installed — skipping local OCR")
        return ""
    except Exception as e:
        logger.warning("image_ocr: tesseract failed for %s: %s", filename, e)
        return ""


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text_from_image(image_bytes: bytes, filename: str) -> str:
    """
    Main entry point.  Tries Groq vision → tesseract → placeholder.

    Returns text formatted with a --- Page: <name> --- marker so the rest
    of the pipeline handles it identically to a PDF page or PPTX slide.
    """
    # 1. Groq vision (best for handwriting)
    text = _ocr_with_groq(image_bytes, filename)
    if text and len(text.strip()) > 30:
        return _format_section(text, filename)

    # 2. Local tesseract (printed text)
    text = _ocr_with_tesseract(image_bytes, filename)
    if text and len(text.strip()) > 30:
        return _format_section(text, filename)

    # 3. Placeholder — at least give the pipeline something
    name = Path(filename).stem
    logger.warning(
        "image_ocr: no text extracted from %s — using placeholder. "
        "Set GROQ_API_KEY to enable handwriting recognition.",
        filename,
    )
    return (
        f"--- Page: {name} ---\n"
        f"[Image '{filename}': text extraction unavailable — "
        "configure GROQ_API_KEY to enable handwriting recognition.]\n"
    )


# ── Diagram / figure description ─────────────────────────────────────────────

_DESCRIBE_SYSTEM = """\
You are an expert technical illustrator and academic assistant.
Your job is to produce a precise, concise description of a diagram or figure
extracted from a lecture slide, for inclusion in study notes.
"""

_DESCRIBE_PROMPT = """\
Describe this diagram/figure from a lecture slide.

Write ONE to THREE sentences covering:
1. What type of diagram it is (circuit, block diagram, graph, waveform, flowchart, table, photo, etc.)
2. The key components, labels, or values visible
3. What concept it illustrates (if inferable)

Rules:
- Be specific: name components ("resistor R1", "op-amp U1"), axis labels, curve names
- Keep it ≤ 60 words
- Output ONLY the description — no preamble, no "This image shows"
"""


def describe_slide_image(image_bytes: bytes, source_label: str = "") -> str:
    """
    Call Groq vision to produce a concise academic caption for a slide figure.
    Returns a short description string, or a generic fallback.
    Falls back gracefully if Groq is unavailable.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        return f"Figure from {source_label}" if source_label else "Figure"

    # Encode as base64 PNG/JPEG
    b64 = base64.b64encode(image_bytes).decode()
    # Detect mime from magic bytes
    if image_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        mime = "image/jpeg"
    else:
        mime = "image/png"

    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
        model = os.environ.get("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _DESCRIBE_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _DESCRIBE_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}",
                                "detail": "low",   # low detail is enough for a caption
                            },
                        },
                    ],
                },
            ],
            max_tokens=120,
            temperature=0.1,
        )
        desc = resp.choices[0].message.content.strip()
        # Strip any leading "This image shows" etc.
        desc = desc.removeprefix("This image shows").removeprefix("This diagram shows").strip()
        if desc.startswith((",", ".")):
            desc = desc[1:].strip()
        logger.info("image_ocr: described '%s' → %s", source_label, desc[:60])
        return desc
    except Exception as e:
        logger.warning("image_ocr: describe_slide_image failed for %s: %s", source_label, e)
        return f"Figure from {source_label}" if source_label else "Figure"
