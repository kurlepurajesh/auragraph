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


# ── Azure Direct HTTP Call (bypasses Semantic Kernel for JSON mode) ────────────

async def _call_azure_json(slides_text: str) -> Optional[list[dict]]:
    """
    Make a direct Azure OpenAI chat completion call with JSON output mode.
    Returns parsed list of topic dicts, or None on failure.
    """
    import os
    import httpx

    endpoint   = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key    = os.environ.get("AZURE_OPENAI_API_KEY",  "")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    api_ver    = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")

    if not endpoint or not api_key or "mock" in endpoint.lower():
        return None

    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_ver}"

    payload = {
        "messages": [
            {"role": "system", "content": _SLIDE_ANALYSIS_SYSTEM},
            {"role": "user",   "content": _SLIDE_ANALYSIS_USER.format(slides=slides_text[:40_000])},
        ],
        "max_tokens": 4096,
        "temperature": 0.1,   # low temperature for structured extraction
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers={"api-key": api_key})
            resp.raise_for_status()
            data    = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # GPT sometimes returns {"topics": [...]} even in json_object mode
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed
            # Unwrap common wrappers
            for key in ("topics", "lecture_topics", "outline", "data"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            return None
    except Exception as e:
        logger.warning("slide_analyzer Azure call failed: %s", e)
        return None


# ── Deterministic Fallback ────────────────────────────────────────────────────

_SLIDE_BOUNDARY = re.compile(r'^---\s*Slide\s+(\d+)(?::\s*(.*?))?\s*---\s*$', re.MULTILINE)


def _deterministic_parse(slides_text: str) -> list[SlideTopic]:
    """
    Parse slide topics from boundary markers without an LLM.
    Groups slides by detected title; skips metadata/empty slides.
    Used as fallback when Azure is unavailable.
    """
    parts = re.split(r'(?=^---\s*Slide\s+\d+)', slides_text, flags=re.MULTILINE)
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

        # Skip metadata / empty slides
        if not body and not title:
            continue
        if title and _META.search(title):
            continue
        if not body and len(title) < 3:
            continue

        display_title = title or f"Slide {m.group(1)}"

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

async def analyse_slides(slides_text: str) -> list[SlideTopic]:
    """
    Extract structured topics from slide text.

    Returns a list of SlideTopic objects in lecture order.
    Uses GPT-4o if Azure is configured, deterministic parser otherwise.
    """
    if not slides_text.strip():
        return []

    # Try LLM extraction
    raw_topics = await _call_azure_json(slides_text)

    if raw_topics:
        topics: list[SlideTopic] = []
        for item in raw_topics:
            if not isinstance(item, dict):
                continue
            topic_name = str(item.get("topic", "")).strip()
            if not topic_name:
                continue
            topics.append(SlideTopic(
                topic=topic_name,
                slide_text=str(item.get("slide_text", "")).strip(),
                key_points=[str(kp) for kp in item.get("key_points", []) if kp],
            ))
        if topics:
            logger.info("slide_analyzer: extracted %d topics via LLM", len(topics))
            return topics

    # Fallback
    logger.info("slide_analyzer: using deterministic fallback parser")
    topics = _deterministic_parse(slides_text)
    logger.info("slide_analyzer: extracted %d topics via fallback", len(topics))
    return topics
