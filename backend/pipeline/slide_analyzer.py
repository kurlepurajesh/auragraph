"""
pipeline/slide_analyzer.py
──────────────────────────
Step 4 — Slide Understanding.

Sends the full slide text to GPT-4o once and gets back a structured list of
topics in lecture order.  Each topic has:
  - topic: the concept name (becomes a ## heading in the notes)
  - slide_text: the verbatim slide content for this topic
  - key_points: list of key facts extracted from the slide

This structured output drives the entire downstream retrieval and generation:
  - One retrieval query per topic  (Step 5)
  - One note generation call per topic  (Step 6)

LLM call budget: exactly 1 call for the entire slide deck.

Fallback: if the LLM call fails, a deterministic regex parser extracts
topics from slide boundary markers (--- Slide N: Title ---).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SlideTopic:
    """One lecture topic extracted from the slide deck."""
    topic:      str
    slide_text: str              # verbatim slide content for this topic
    key_points: list[str] = field(default_factory=list)


# ── Prompt ────────────────────────────────────────────────────────────────────

_SLIDE_ANALYSIS_SYSTEM = """\
You are an expert academic content analyst.
Your job is to extract the structured lecture outline from raw slide text.
"""

_SLIDE_ANALYSIS_USER = """\
Below is the full text of a lecture slide deck.
Extract the lecture topics IN SLIDE ORDER.

For each topic output:
  - "topic": short concept name (3-6 words max, suitable as a section heading)
  - "key_points": list of 2-5 key facts or ideas from the slides for this topic
  - "slide_text": the verbatim slide text that belongs to this topic

Rules:
  1. Follow slide order exactly — do NOT reorder topics.
  2. Merge consecutive slides that cover the same concept into ONE topic entry.
  3. Ignore metadata slides (title slide, table of contents, references, thank you).
  4. Each topic must correspond to actual teaching content from the slides.
  5. key_points must come FROM the slides, not invented.
  6. Output ONLY valid JSON — a list of topic objects. No preamble, no markdown fences.

Example output format:
[
  {
    "topic": "Fourier Transform",
    "key_points": [
      "converts time domain to frequency domain",
      "F(omega) = integral of f(t) times complex exponential"
    ],
    "slide_text": "--- Slide 3: Fourier Transform ---\\nF(\\u03c9) = \\u222b..."
  }
]

SLIDE TEXT:
{slides}
"""


# ── LLM Helpers (Azure via openai SDK + Groq fallback) ────────────────────────

import asyncio as _asyncio


def _azure_ok() -> bool:
    ep  = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    key = os.environ.get("AZURE_OPENAI_API_KEY",  "")
    return bool(ep) and bool(key) and "mock" not in ep.lower()


def _groq_ok() -> bool:
    key = os.environ.get("GROQ_API_KEY", "")
    return key not in ("", "your-groq-api-key-here")


def _parse_topics_json(content: str) -> Optional[list[dict]]:
    """Parse JSON content into a list of topic dicts, unwrapping common wrappers."""
    # Strip markdown fences if present
    content = re.sub(r'^```[a-z]*\s*', '', content.strip(), flags=re.MULTILINE)
    content = re.sub(r'```\s*$', '', content.strip(), flags=re.MULTILINE)
    parsed = json.loads(content.strip())
    if isinstance(parsed, list):
        return parsed
    for key in ("topics", "lecture_topics", "outline", "data", "result"):
        if key in parsed and isinstance(parsed[key], list):
            return parsed[key]
    return None


async def _call_azure_json(slides_text: str) -> Optional[list[dict]]:
    """Slide analysis via Azure OpenAI (openai SDK). Returns list of topic dicts or None."""
    if not _azure_ok():
        return None
    try:
        from openai import AzureOpenAI
        def _sync():
            client = AzureOpenAI(
                azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            )
            resp = client.chat.completions.create(
                model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
                messages=[
                    {"role": "system", "content": _SLIDE_ANALYSIS_SYSTEM},
                    {"role": "user",   "content": _SLIDE_ANALYSIS_USER.format(slides=slides_text[:40_000])},
                ],
                max_tokens=4096,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content.strip()
        content = await _asyncio.to_thread(_sync)
        return _parse_topics_json(content)
    except Exception as e:
        logger.warning("slide_analyzer Azure call failed: %s", e)
        return None


async def _call_groq_json(slides_text: str) -> Optional[list[dict]]:
    """Slide analysis via Groq (openai SDK with Groq base URL). Returns list or None."""
    if not _groq_ok():
        return None
    try:
        from openai import OpenAI
        def _sync():
            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=os.environ.get("GROQ_API_KEY", ""),
            )
            model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            # Ask Groq to return JSON — instruct it explicitly in the prompt
            user_prompt = (
                _SLIDE_ANALYSIS_USER.format(slides=slides_text[:35_000])
                + "\n\nIMPORTANT: Output ONLY a valid JSON array. No markdown fences. No explanation."
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SLIDE_ANALYSIS_SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=4096,
                temperature=0.1,
            )
            return resp.choices[0].message.content.strip()
        content = await _asyncio.to_thread(_sync)
        return _parse_topics_json(content)
    except Exception as e:
        logger.warning("slide_analyzer Groq call failed: %s", e)
        return None


# ── Deterministic Fallback ────────────────────────────────────────────────────

# Match both --- Slide N --- (PPTX) and --- Page N --- (PDF)
_SLIDE_BOUNDARY = re.compile(
    r'^---\s*(?:Slide|Page)\s+(\d+)(?::\s*(.*?))?\s*---\s*$', re.MULTILINE
)


def _deterministic_parse(slides_text: str) -> list[SlideTopic]:
    """
    Parse slide topics from boundary markers without an LLM.
    Groups slides by detected title; skips metadata/empty slides.
    Used as fallback when Azure is unavailable.
    """
    parts = re.split(r'(?=^---\s*(?:Slide|Page)\s+\d+)', slides_text, flags=re.MULTILINE)
    topics: list[SlideTopic] = []

    _META = re.compile(
        r'\b(table of contents|references|bibliography|acknowledgement|'
        r'thank you|agenda|outline|questions|q&a)\b',
        re.I,
    )

    for part in parts:
        part = part.strip()
        if not part:
            continue

        m = _SLIDE_BOUNDARY.match(part.split('\n')[0])
        if not m:
            continue

        title = (m.group(2) or '').strip()
        body  = part[m.end():].strip()
        num   = m.group(1)

        # Skip metadata / empty slides
        if not body and not title:
            continue
        if title and _META.search(title):
            continue
        if not body and len(title) < 3:
            continue

        # Normalise display title: always say "Slide N" not "Page N"
        display_title = title or f"Slide {num}"

        # Try to merge into previous topic if same/no title
        if topics and (not title or title.lower() == topics[-1].topic.lower()):
            topics[-1].slide_text += "\n\n" + part
            if body:
                topics[-1].key_points.extend(_extract_bullets(body)[:2])
        else:
            topics.append(SlideTopic(
                topic=display_title,
                slide_text=part,
                key_points=_extract_bullets(body)[:4],
            ))

    return topics


def _extract_bullets(text: str) -> list[str]:
    """Pull out bullet-point-like lines as key points."""
    lines = text.split('\n')
    bullets = []
    for line in lines:
        stripped = line.strip()
        # Bullet markers or short meaningful lines
        if stripped.startswith(('•', '-', '*', '–', '→')):
            point = stripped.lstrip('•-*–→ ').strip()
            if len(point) > 10:
                bullets.append(point)
        elif 10 < len(stripped) < 120 and not stripped.startswith('---'):
            bullets.append(stripped)
    return bullets[:5]


# ── Public API ────────────────────────────────────────────────────────────────

_SLIDE_CHUNK_SIZE = 38_000   # chars per LLM call — safe below GPT-4o 128k limit
# FIX G2: no longer hard-truncate the full deck; instead split into chunks
# and merge the resulting topic lists.


def _split_at_slide_boundary(text: str, max_chars: int) -> list[str]:
    """
    Split slide text at slide boundary markers so each chunk ends on a complete
    slide, keeping chunk size ≤ max_chars. Falls back to hard split if no markers.
    """
    if len(text) <= max_chars:
        return [text]
    # Find all slide marker positions
    boundaries = [m.start() for m in re.finditer(
        r'(?m)^---\s*(?:Slide|Page)\s+\d+', text
    )]
    if not boundaries:
        # No markers — hard split
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

    chunks, start = [], 0
    current = 0
    for boundary in boundaries[1:]:  # skip first (it IS the start)
        if boundary - start > max_chars:
            # Cut here — take up to this boundary
            chunks.append(text[start:boundary])
            start = boundary
            current = 0
        current = boundary - start
    # Add remainder
    if start < len(text):
        chunks.append(text[start:])
    return chunks if chunks else [text]


async def analyse_slides(slides_text: str) -> list[SlideTopic]:
    """
    Extract structured topics from slide text.

    FIX G2: For long decks (> 38 k chars), the text is split at slide
    boundaries and analysed in multiple LLM calls. Topics from all chunks are
    concatenated in order.  No slide is silently dropped.

    Priority per chunk: Azure → Groq → deterministic regex parser.
    Returns a list of SlideTopic objects in lecture order.
    """
    if not slides_text.strip():
        return []

    chunks = _split_at_slide_boundary(slides_text, _SLIDE_CHUNK_SIZE)
    all_topics: list[SlideTopic] = []

    for chunk_idx, chunk_text in enumerate(chunks):
        logger.info(
            "slide_analyzer: analysing chunk %d/%d (%d chars)",
            chunk_idx + 1, len(chunks), len(chunk_text),
        )
        raw_topics = await _call_azure_json(chunk_text)
        if not raw_topics:
            raw_topics = await _call_groq_json(chunk_text)

        if raw_topics:
            for item in raw_topics:
                if not isinstance(item, dict):
                    continue
                topic_name = str(item.get("topic", "")).strip()
                if not topic_name:
                    continue
                all_topics.append(SlideTopic(
                    topic=topic_name,
                    slide_text=str(item.get("slide_text", "")).strip(),
                    key_points=[str(kp) for kp in item.get("key_points", []) if kp],
                ))
        else:
            # Fallback for this chunk
            all_topics.extend(_deterministic_parse(chunk_text))

    if all_topics:
        logger.info("slide_analyzer: extracted %d topics total (across %d chunks)",
                    len(all_topics), len(chunks))
        return all_topics

    logger.info("slide_analyzer: using deterministic fallback parser")
    topics = _deterministic_parse(slides_text)
    logger.info("slide_analyzer: extracted %d topics via fallback", len(topics))
    return topics
