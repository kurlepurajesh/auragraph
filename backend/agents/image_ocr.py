"""
backend/agents/image_ocr.py
────────────────────────────
Extracts text from handwritten or printed notes images, and describes
slide figures for embedding into study notes.

Fixes in v5:
  E1 – describe_slide_image was synchronous; callers must now wrap it with
       asyncio.to_thread (done in main.py upload handler).
  E2 – No image size limit before sending to Groq. Now resizes to max 1024px
       on the longest side before base64-encoding (~200 KB vs ~5 MB).
  E3 – WebP magic bytes not detected → mislabelled as image/png. Fixed.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp',
    '.bmp', '.tiff', '.tif', '.heic', '.heif',
}

_MIME_MAP = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png',  '.webp': 'image/webp',
    '.bmp': 'image/bmp',  '.tiff': 'image/tiff',
    '.tif': 'image/tiff', '.heic': 'image/heic',
    '.heif': 'image/heif',
}

# ── OCR prompts ───────────────────────────────────────────────────────────────

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

# ── Describe prompts ──────────────────────────────────────────────────────────

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

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_image_file(filename: str) -> bool:
    return Path(filename.lower()).suffix in IMAGE_EXTENSIONS


def _guess_mime(filename: str) -> str:
    return _MIME_MAP.get(Path(filename.lower()).suffix, 'image/jpeg')


def _detect_mime_from_bytes(data: bytes) -> str:
    """
    FIX E3: Detect image MIME type from magic bytes rather than filename.
    Handles PNG, JPEG, WebP, GIF, BMP. Falls back to image/jpeg.
    """
    if data[:4] == b'\x89PNG':
        return 'image/png'
    if data[:2] == b'\xff\xd8':
        return 'image/jpeg'
    # WebP: starts with RIFF....WEBP
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:2] == b'BM':
        return 'image/bmp'
    return 'image/jpeg'


def _resize_for_api(image_bytes: bytes, max_px: int = 1024) -> tuple[bytes, str]:
    """
    FIX E2: Resize image so longest side ≤ max_px before encoding.
    Returns (resized_bytes, mime_type). Falls back to original on error.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) <= max_px:
            # Already small enough — re-encode as JPEG to compress
            buf = io.BytesIO()
            img.convert('RGB').save(buf, format='JPEG', quality=85)
            return buf.getvalue(), 'image/jpeg'
        # Resize keeping aspect ratio
        scale = max_px / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=85)
        logger.debug("Resized image %dx%d → %dx%d for API", w, h, new_w, new_h)
        return buf.getvalue(), 'image/jpeg'
    except Exception as e:
        logger.debug("Image resize failed (%s) — using original", e)
        return image_bytes, _detect_mime_from_bytes(image_bytes)


def _convert_heic(image_bytes: bytes) -> tuple[bytes, str]:
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=95)
        return buf.getvalue(), 'image/jpeg'
    except Exception as e:
        logger.debug("HEIC conversion failed (%s) — passing raw bytes", e)
        return image_bytes, 'image/heic'


def _format_section(text: str, filename: str) -> str:
    name = Path(filename).stem
    return f"--- Page: {name} ---\n{text.strip()}\n"


# ── Groq vision OCR ───────────────────────────────────────────────────────────

def _ocr_with_groq(image_bytes: bytes, filename: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        return ""

    fname_lower = filename.lower()
    if fname_lower.endswith(('.heic', '.heif')):
        image_bytes, mime = _convert_heic(image_bytes)
    else:
        # FIX E2: resize before sending
        image_bytes, mime = _resize_for_api(image_bytes)

    b64 = base64.b64encode(image_bytes).decode()

    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
        model  = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _OCR_SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": _OCR_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{b64}",
                        "detail": "high",
                    }},
                ]},
            ],
            max_tokens=4096,
            temperature=0.1,
        )
        result = resp.choices[0].message.content.strip()
        logger.info("image_ocr: Groq OCR extracted %d chars from %s", len(result), filename)
        return result
    except Exception as e:
        logger.warning("image_ocr: Groq OCR failed for %s: %s", filename, e)
        return ""


# ── pytesseract OCR ───────────────────────────────────────────────────────────

def _ocr_with_tesseract(image_bytes: bytes, filename: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) < 1200:
            scale = 1200 / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        text = pytesseract.image_to_string(img, config='--psm 6 --oem 3').strip()
        if text:
            logger.info("image_ocr: tesseract extracted %d chars from %s", len(text), filename)
        return text
    except ImportError:
        return ""
    except Exception as e:
        logger.warning("image_ocr: tesseract failed for %s: %s", filename, e)
        return ""


# ── Public: OCR entry point ───────────────────────────────────────────────────

def extract_text_from_image(image_bytes: bytes, filename: str) -> str:
    """
    Groq vision → tesseract → placeholder.
    NOTE (E1): This function is synchronous. Callers in async context must use
    `await asyncio.to_thread(extract_text_from_image, data, fname)`.
    """
    text = _ocr_with_groq(image_bytes, filename)
    if text and len(text.strip()) > 30:
        return _format_section(text, filename)

    text = _ocr_with_tesseract(image_bytes, filename)
    if text and len(text.strip()) > 30:
        return _format_section(text, filename)

    name = Path(filename).stem
    logger.warning("image_ocr: no text from %s — placeholder used", filename)
    return (
        f"--- Page: {name} ---\n"
        f"[Image '{filename}': text extraction unavailable — "
        "configure GROQ_API_KEY to enable handwriting recognition.]\n"
    )


# ── Public: Figure description ────────────────────────────────────────────────

def describe_slide_image(image_bytes: bytes, source_label: str = "") -> str:
    """
    Call Groq vision to produce a concise academic caption for a slide figure.

    FIX E1: This function is SYNCHRONOUS (blocking network I/O).
            Callers in async context MUST wrap with asyncio.to_thread():
            `desc = await asyncio.to_thread(describe_slide_image, data, label)`

    FIX E2: Image is resized to max 1024px before encoding.
    FIX E3: MIME type detected from magic bytes, not filename.

    Returns a short description string, or a generic fallback.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        return f"Figure from {source_label}" if source_label else "Figure"

    # FIX E2: resize to max 1024px before encoding
    data, mime = _resize_for_api(image_bytes, max_px=1024)
    # FIX E3: detect from magic bytes (override whatever PIL gave us)
    mime = _detect_mime_from_bytes(data)

    b64 = base64.b64encode(data).decode()

    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
        model  = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _DESCRIBE_SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": _DESCRIBE_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{b64}",
                        "detail": "low",
                    }},
                ]},
            ],
            max_tokens=120,
            temperature=0.1,
        )
        desc = resp.choices[0].message.content.strip()
        desc = desc.removeprefix("This image shows").removeprefix(
            "This diagram shows").strip()
        if desc.startswith((",", ".")):
            desc = desc[1:].strip()
        logger.info("image_ocr: described '%s' → %s", source_label, desc[:60])
        return desc
    except Exception as e:
        logger.warning("image_ocr: describe failed for %s: %s", source_label, e)
        return f"Figure from {source_label}" if source_label else "Figure"
