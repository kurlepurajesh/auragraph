"""
agents/image_ocr.py — Azure AI Vision + Groq vision fallback
──────────────────────────────────────────────────────────────
Extracts text from handwritten/printed notes images, and describes
slide figures for embedding into study notes.

Priority (OCR):
  1. Azure AI Vision (dense captions + OCR) — AZURE_VISION_ENDPOINT + KEY
  2. Groq vision (llama-4-scout)             — GROQ_API_KEY
  3. pytesseract                             — local
  4. Placeholder text

Priority (figure description):
  1. Azure AI Vision image analysis
  2. Groq vision
  3. Generic fallback string
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

# ── prompts ───────────────────────────────────────────────────────────────────

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
• Start directly with the text — no preamble
• Use blank lines between sections
• Preserve indentation hierarchy with bullets

Do NOT skip, paraphrase, or summarise anything.
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


# ── helpers ───────────────────────────────────────────────────────────────────

def is_image_file(filename: str) -> bool:
    return Path(filename.lower()).suffix in IMAGE_EXTENSIONS


def _detect_mime(data: bytes) -> str:
    if data[:4] == b'\x89PNG':          return 'image/png'
    if data[:2] == b'\xff\xd8':         return 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'image/webp'
    if data[:6] in (b'GIF87a', b'GIF89a'): return 'image/gif'
    if data[:2] == b'BM':               return 'image/bmp'
    return 'image/jpeg'


def _resize(image_bytes: bytes, max_px: int = 1024) -> tuple[bytes, str]:
    """Resize longest side to max_px and re-encode as JPEG. Falls back on error."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=85)
        return buf.getvalue(), 'image/jpeg'
    except Exception as e:
        logger.debug("Image resize failed (%s) — using original", e)
        return image_bytes, _detect_mime(image_bytes)


def _convert_heic(data: bytes) -> tuple[bytes, str]:
    try:
        import pillow_heif; pillow_heif.register_heif_opener()
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=95)
        return buf.getvalue(), 'image/jpeg'
    except Exception:
        return data, 'image/heic'


def _format_section(text: str, filename: str) -> str:
    name = Path(filename).stem
    return f"--- Page: {name} ---\n{text.strip()}\n"


# ── Azure AI Vision ──────────────────────────────────────────────────────────

def _vision_configured() -> bool:
    ep  = os.environ.get("AZURE_VISION_ENDPOINT", "")
    key = os.environ.get("AZURE_VISION_KEY", "")
    return bool(ep and key
                and "placeholder" not in ep.lower()
                and "your-" not in key.lower())


def _ocr_with_azure_vision(image_bytes: bytes, filename: str) -> str:
    """
    Use Azure AI Vision Read OCR API to extract text from an image.
    Returns extracted text or empty string on failure.
    This is synchronous; callers in async context must use asyncio.to_thread().
    """
    if not _vision_configured():
        return ""
    try:
        from azure.ai.vision.imageanalysis import ImageAnalysisClient
        from azure.ai.vision.imageanalysis.models import VisualFeatures
        from azure.core.credentials import AzureKeyCredential

        endpoint = os.environ.get("AZURE_VISION_ENDPOINT", "").rstrip("/")
        key      = os.environ.get("AZURE_VISION_KEY", "")

        data, _ = _resize(image_bytes, max_px=4096)   # Vision supports up to 4096px
        client = ImageAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        result = client.analyze(
            image_data=data,
            visual_features=[VisualFeatures.READ],
        )
        if not result.read or not result.read.blocks:
            return ""
        lines = []
        for block in result.read.blocks:
            for line in block.lines:
                lines.append(line.text)
        text = "\n".join(lines).strip()
        logger.info("Azure Vision OCR: extracted %d chars from %s", len(text), filename)
        return text
    except Exception as e:
        logger.warning("Azure Vision OCR failed for %s: %s", filename, e)
        return ""


def _describe_with_azure_vision(image_bytes: bytes, source_label: str) -> str:
    """
    Use Azure AI Vision dense captioning + tag analysis to describe a slide figure.
    Returns a concise description string or empty string on failure.
    Synchronous — wrap with asyncio.to_thread() in async contexts.
    """
    if not _vision_configured():
        return ""
    try:
        from azure.ai.vision.imageanalysis import ImageAnalysisClient
        from azure.ai.vision.imageanalysis.models import VisualFeatures
        from azure.core.credentials import AzureKeyCredential

        endpoint = os.environ.get("AZURE_VISION_ENDPOINT", "").rstrip("/")
        key      = os.environ.get("AZURE_VISION_KEY", "")

        data, _ = _resize(image_bytes, max_px=1024)
        client = ImageAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        result = client.analyze(
            image_data=data,
            visual_features=[VisualFeatures.DENSE_CAPTIONS, VisualFeatures.TAGS],
        )

        parts = []
        # Primary: dense caption (highest confidence first)
        if result.dense_captions and result.dense_captions.list:
            top = max(result.dense_captions.list, key=lambda c: c.confidence or 0)
            if top.text:
                parts.append(top.text.rstrip("."))

        # Supplement with top relevant tags (skip generic ones)
        _SKIP_TAGS = {"screenshot", "text", "font", "white", "black", "line", "number",
                      "diagram", "image", "photo", "illustration"}
        if result.tags and result.tags.list:
            good_tags = [
                t.name for t in result.tags.list
                if (t.confidence or 0) > 0.7 and t.name.lower() not in _SKIP_TAGS
            ]
            if good_tags:
                parts.append("Showing: " + ", ".join(good_tags[:5]))

        desc = ". ".join(parts).strip() if parts else ""
        if desc:
            logger.info("Azure Vision describe: '%s' → %s", source_label, desc[:80])
        return desc
    except Exception as e:
        logger.warning("Azure Vision describe failed for %s: %s", source_label, e)
        return ""


# ── Groq vision fallback ─────────────────────────────────────────────────────

def _ocr_with_groq(image_bytes: bytes, filename: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        return ""
    fname_lower = filename.lower()
    if fname_lower.endswith(('.heic', '.heif')):
        image_bytes, mime = _convert_heic(image_bytes)
    else:
        image_bytes, mime = _resize(image_bytes)
    mime = _detect_mime(image_bytes)
    b64  = base64.b64encode(image_bytes).decode()
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
                        "url": f"data:{mime};base64,{b64}", "detail": "high",
                    }},
                ]},
            ],
            max_tokens=4096, temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
        logger.info("Groq OCR: extracted %d chars from %s", len(text), filename)
        return text
    except Exception as e:
        logger.warning("Groq OCR failed for %s: %s", filename, e)
        return ""


def _describe_with_groq(image_bytes: bytes, source_label: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        return ""
    data, mime = _resize(image_bytes, max_px=1024)
    mime = _detect_mime(data)
    b64  = base64.b64encode(data).decode()
    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
        model  = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": _DESCRIBE_PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{b64}", "detail": "low",
                    }},
                ]},
            ],
            max_tokens=120, temperature=0.1,
        )
        desc = resp.choices[0].message.content.strip()
        desc = desc.removeprefix("This image shows").removeprefix("This diagram shows").strip()
        if desc.startswith((",", ".")):
            desc = desc[1:].strip()
        return desc
    except Exception as e:
        logger.warning("Groq describe failed for %s: %s", source_label, e)
        return ""


# ── pytesseract fallback ─────────────────────────────────────────────────────

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
            logger.info("tesseract: extracted %d chars from %s", len(text), filename)
        return text
    except ImportError:
        return ""
    except Exception as e:
        logger.warning("tesseract failed for %s: %s", filename, e)
        return ""


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text_from_image(image_bytes: bytes, filename: str) -> str:
    """
    Azure AI Vision OCR → Groq vision → tesseract → placeholder.
    SYNCHRONOUS — callers in async context must use asyncio.to_thread().
    """
    # 1. Azure AI Vision (preferred — highest quality OCR)
    text = _ocr_with_azure_vision(image_bytes, filename)
    if text and len(text.strip()) > 30:
        return _format_section(text, filename)

    # 2. Groq vision
    text = _ocr_with_groq(image_bytes, filename)
    if text and len(text.strip()) > 30:
        return _format_section(text, filename)

    # 3. pytesseract
    text = _ocr_with_tesseract(image_bytes, filename)
    if text and len(text.strip()) > 30:
        return _format_section(text, filename)

    # 4. Placeholder
    name = Path(filename).stem
    logger.warning("image_ocr: no text from %s — placeholder used", filename)
    return (
        f"--- Page: {name} ---\n"
        f"[Image '{filename}': text extraction unavailable. "
        "Configure AZURE_VISION_ENDPOINT or GROQ_API_KEY to enable OCR.]\n"
    )


def describe_slide_image(image_bytes: bytes, source_label: str = "") -> str:
    """
    Azure AI Vision dense captions → Groq vision → generic fallback.
    SYNCHRONOUS — callers in async context must use asyncio.to_thread().
    """
    # 1. Azure AI Vision (preferred)
    desc = _describe_with_azure_vision(image_bytes, source_label)
    if desc:
        return desc

    # 2. Groq vision fallback
    desc = _describe_with_groq(image_bytes, source_label)
    if desc:
        return desc

    # 3. Generic fallback
    return f"Figure from {source_label}" if source_label else "Figure"
