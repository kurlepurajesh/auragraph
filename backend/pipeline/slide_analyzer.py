# -*- coding: utf-8 -*-
"""
pipeline/slide_analyzer.py
--------------------------
Step 4 - Slide Understanding.

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


# -- Prompt --------------------------------------------------------------------

_SLIDE_ANALYSIS_SYSTEM = """\
You are an expert academic content analyst.
Your job is to extract the structured lecture outline from raw slide text.

Source text quality - YOU are the ground truth:
The input may come from OCR of handwritten notes or scanned slides. The source text
tells you the TOPIC and rough content; your own knowledge determines what is correct.

Before writing any key_point, verify it against what you know:
  - Formulas    - verify every operator, sign, Jacobian, fraction, exponent.
  - Definitions - check for missing conditions or qualifiers.
  - Claims      - check direction, scope, and completeness.

If the source has an error, write the CORRECT statement in key_points - not the
erroneous source version. OCR math is often garbled ("E[X] = mu", "integral from
0 to T", garbled fractions) - reconstruct the correct expression from context.
"""

_SLIDE_ANALYSIS_USER = """\
Below is the full text of a lecture slide deck.
Extract the lecture topics IN SLIDE ORDER.

IMPORTANT: The text may contain multiple files separated by markers like:
  ============================================================
  === FILE: filename.pdf ===
  ============================================================
Each file is a separate set of slides. You MUST extract topics from ALL files.
Do NOT stop after the first file. Every file's content must be represented in your output.

For each topic output:
  - "topic": short concept name (3-6 words max, suitable as a section heading)
  - "key_points": list of ALL key facts, formulas, definitions, algorithms, and properties
    from the slides for this topic. Do NOT cap or summarise - include every distinct
    concept so the note generator can cover the slides completely.
  - "slide_text": the verbatim slide text that belongs to this topic

Rules:
  1. Follow slide order exactly - do NOT reorder topics.
  2. Merge consecutive slides that cover the same concept into ONE topic entry.
  3. Ignore metadata slides: cover page, title slide, table of contents, references,
     bibliography, agenda, outline, thank you, acknowledgements, course overview,
     learning objectives. If a slide has only a course/lecture title and author name
     with no teaching content, skip it.
  4. Each topic must correspond to actual teaching content from the slides.
  5. EVERY topic MUST have non-empty "slide_text" containing the verbatim slide
     content for that topic.  If a topic genuinely has no slide text, omit it
     entirely rather than returning an entry with an empty slide_text field.
  6. key_points must represent the CORRECT mathematical or conceptual statement.
     If the slide text has OCR artifacts or garbled math, interpret using your own
     knowledge - state the formula/concept correctly, not as the OCR garbled it.
  7. FILE COVERAGE (critical): If multiple files are present, ensure at least one
     topic per file is present in your output. Never silently drop an entire file.
  8. Output ONLY valid JSON in this exact format - a JSON object with a "topics" key containing the array.
     No preamble, no markdown fences, no extra keys.

Required output format:
{"topics": [
  {
    "topic": "Fourier Transform",
    "key_points": [
      "converts time domain to frequency domain",
      "F(omega) = integral of f(t) times complex exponential"
    ],
    "slide_text": "--- Slide 3: Fourier Transform ---\\nContent here..."
  }
]}

SLIDE TEXT:
{slides}
"""


# -- LLM Helpers (Azure via openai SDK + Groq fallback) ------------------------

import asyncio as _asyncio


def _azure_ok() -> bool:
    ep  = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    key = os.environ.get("AZURE_OPENAI_API_KEY",  "")
    # FIX (round 4): mirror main.py - also reject "placeholder" endpoints/keys
    return (
        bool(ep) and bool(key)
        and "mock"        not in ep.lower()
        and "placeholder" not in ep.lower()
        and "placeholder" not in key.lower()
    )


def _groq_ok() -> bool:
    key = os.environ.get("GROQ_API_KEY", "")
    return key not in ("", "your-groq-api-key-here")


def _parse_topics_json(content: str) -> Optional[list[dict]]:
    """Parse JSON content into a list of topic dicts, unwrapping common wrappers.

    Handles:
      - bare JSON arrays
      - objects with well-known keys (topics, lecture_topics, outline, ...)
      - objects with any unknown key whose value is a list  (catch-all)
      - malformed/truncated output - scans for the first [ ... ] array fragment
    """
    # Strip markdown fences if present
    content = re.sub(r'^```[a-z]*\s*', '', content.strip(), flags=re.MULTILINE)
    content = re.sub(r'```\s*$', '', content.strip(), flags=re.MULTILINE)
    content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract the first JSON array embedded anywhere in the text
        m = re.search(r'\[', content)
        if m:
            try:
                # json.JSONDecoder.raw_decode finds the largest valid object starting at pos
                decoder = json.JSONDecoder()
                parsed, _ = decoder.raw_decode(content, m.start())
            except json.JSONDecodeError:
                logger.warning("slide_analyzer: JSON parse failed; raw content head: %r", content[:300])
                return None
        else:
            logger.warning("slide_analyzer: no JSON array found; raw content head: %r", content[:300])
            return None

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        # Well-known wrapper keys first
        for key in ("topics", "lecture_topics", "outline", "data", "result", "items"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        # Catch-all: return the first non-empty list value found
        for val in parsed.values():
            if isinstance(val, list) and val:
                return val
    return None


async def _call_azure_json(slides_text: str) -> Optional[list[dict]]:
    """
    Slide analysis via Azure OpenAI - true async httpx.
    FIX C1: was asyncio.to_thread(AzureOpenAI(...)), now httpx.AsyncClient.
    Includes one 429 retry with Retry-After back-off.
    """
    if not _azure_ok():
        return None
    try:
        import httpx
        endpoint   = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        api_key    = os.environ.get("AZURE_OPENAI_API_KEY",  "")
        api_ver    = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_ver}"
        user_content = _SLIDE_ANALYSIS_USER.replace("{slides}", slides_text)  # no inner truncation - chunking already limits size
        payload = {
            "messages": [
                {"role": "system", "content": _SLIDE_ANALYSIS_SYSTEM},
                {"role": "user",   "content": user_content},
            ],
            "max_tokens":     16000,
            "temperature":    0.1,
            "response_format": {"type": "json_object"},  # forces valid JSON object output
        }
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        for attempt in range(2):
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 429 and attempt == 0:
                wait = int(resp.headers.get("Retry-After", "10"))
                logger.warning("slide_analyzer Azure 429 - retrying in %d s", wait)
                await _asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            logger.info("slide_analyzer Azure raw response (first 300 chars): %r", raw[:300])
            topics = _parse_topics_json(raw)
            logger.info("slide_analyzer Azure parsed %s topics", len(topics) if topics else 0)
            return topics
    except Exception as e:
        logger.warning("slide_analyzer Azure call failed: %s", e)
    return None


async def _call_groq_json(slides_text: str) -> Optional[list[dict]]:
    """
    Slide analysis via Groq - true async httpx.
    FIX C1: was asyncio.to_thread(OpenAI(...)), now httpx.AsyncClient.
    Includes one 429 retry with Retry-After back-off.
    """
    if not _groq_ok():
        return None
    try:
        import httpx
        api_key = os.environ.get("GROQ_API_KEY", "")
        model   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        user_prompt = (
            # no inner truncation - chunking already limits size
            _SLIDE_ANALYSIS_USER.replace("{slides}", slides_text)
            + "\n\nIMPORTANT: Output ONLY valid JSON with a \"topics\" key. No markdown fences. No explanation."
        )
        payload = {
            "model":       model,
            "messages":    [
                {"role": "system", "content": _SLIDE_ANALYSIS_SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            "max_tokens":  32_000,   # llama-3.3-70b-versatile supports 32k; 8192 caused truncated JSON on large chunks
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        for attempt in range(2):
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload, headers=headers,
                )
            if resp.status_code == 429 and attempt == 0:
                wait = int(resp.headers.get("Retry-After", "6"))
                logger.warning("slide_analyzer Groq 429 - retrying in %d s", wait)
                await _asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            logger.info("slide_analyzer Groq raw response (first 300 chars): %r", raw[:300])
            topics = _parse_topics_json(raw)
            logger.info("slide_analyzer Groq parsed %s topics", len(topics) if topics else 0)
            return topics
    except Exception as e:
        logger.warning("slide_analyzer Groq call failed: %s", e)
    return None


# -- Deterministic Fallback ----------------------------------------------------

# Match --- Slide N --- (PPTX), --- Page N --- (PDF), and --- Page: name --- (image OCR)
_SLIDE_BOUNDARY = re.compile(
    r'^---\s*(?:Slide|Page)\s+(\d+)(?::\s*(.*?))?\s*---\s*$'
    r'|^---\s*Page:\s*([^\-].*?)\s*---\s*$',
    re.MULTILINE,
)


def _deterministic_parse(slides_text: str) -> list[SlideTopic]:
    """
    Parse slide topics from boundary markers without an LLM.
    Groups slides by detected title; skips metadata/empty slides.
    Used as fallback when Azure is unavailable.
    """
    parts = re.split(
        r'(?=^---\s*(?:Slide\s+\d+|Page(?:\s+\d+|:)))',
        slides_text, flags=re.MULTILINE
    )
    topics: list[SlideTopic] = []

    _META = re.compile(
        r'\b(table of contents|references|bibliography|acknowledgement|'
        r'thank you|agenda|outline|questions|q&a|title page|cover page|'
        r'course overview|learning objectives|about this course|welcome to|'
        r'course introduction|lecture overview|recap|revision)\b'
        r'|^(cover|title|contents|intro|introduction)$',
        re.I,
    )

    for part in parts:
        part = part.strip()
        if not part:
            continue

        m = _SLIDE_BOUNDARY.match(part.split('\n')[0])
        if not m:
            continue

        body = part[m.end():].strip()

        if m.group(1):  # numbered format: --- Slide N --- / --- Page N ---
            title = (m.group(2) or '').strip()
            num   = m.group(1)
            display_title = title or f"Slide {num}"
        else:           # image OCR format: --- Page: filename ---
            title = (m.group(3) or '').strip()
            display_title = title or "Image Notes"
            num   = None

        # Skip metadata / empty slides
        if not body and not title:
            continue
        if title and _META.search(title):
            continue
        if not body and len(title) < 3:
            continue
        # Skip cover/title pages: body has no teaching content (no colons, bullets, or
        # alphanumeric formulas) and is very short - typically just author + date + publisher
        _COVER_BODY = re.compile(
            r'^[\s\w,.\---()/(c)(r)(tm)@#$%&\'"!?]+$', re.DOTALL
        )
        if (body and len(body) < 150 and _COVER_BODY.match(body)
                and not re.search(r'[=+\-*/^sumintegraldsqrt]|\\[a-zA-Z]\{|[alphabetagammadeltaepsilonzetathetalambdamupirhosigmaphipsiomega]', body)):
            continue

        # Try to merge into previous topic if same/no title
        if topics and (not title or title.lower() == topics[-1].topic.lower()):
            topics[-1].slide_text += "\n\n" + part
            if body:
                topics[-1].key_points.extend(_extract_bullets(body)[:2])
        else:
            topics.append(SlideTopic(
                topic=display_title,
                slide_text=part,
                key_points=_extract_bullets(body),  # no cap -- include all key points
            ))

    return topics


def _extract_bullets(text: str) -> list[str]:
    """Pull out bullet-point-like lines as key points."""
    lines = text.split('\n')
    bullets = []
    for line in lines:
        stripped = line.strip()
        # Bullet markers or short meaningful lines
        if stripped.startswith(('-', '-', '*', '-', '->')):
            point = stripped.lstrip('--*--> ').strip()
            if len(point) > 10:
                bullets.append(point)
        elif 10 < len(stripped) < 120 and not stripped.startswith('---'):
            bullets.append(stripped)
    return bullets[:5]


# -- Public API ----------------------------------------------------------------

_SLIDE_CHUNK_SIZE = 32_000   # chars per LLM call - increased from 24k to reduce cross-chunk topic splits
# FIX G2: no longer hard-truncate the full deck; instead split into chunks
# and merge the resulting topic lists.


def _split_at_slide_boundary(text: str, max_chars: int) -> list[str]:
    """
    Split slide text at slide boundary markers so each chunk ends on a complete
    slide, keeping chunk size <= max_chars. Falls back to hard split if no markers.
    Handles all three marker formats:
      --- Slide N ---     (PPTX)
      --- Page N ---      (PDF)
      --- Page: name ---  (image OCR)
    """
    if len(text) <= max_chars:
        return [text]
    # Find all slide marker positions (all three formats)
    boundaries = [m.start() for m in re.finditer(
        r'(?m)^---\s*(?:(?:Slide|Page)\s+\d+|Page:\s*[^\-\n])', text
    )]
    if not boundaries:
        # No markers - hard split
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

    chunks, start = [], 0
    for boundary in boundaries[1:]:  # skip first (it IS the start)
        if boundary - start >= max_chars:  # >= so a chunk of exactly max_chars still splits
            # Accumulated content since last cut exceeds limit - cut here
            chunks.append(text[start:boundary])
            start = boundary
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

    Priority per chunk: Azure -> Groq -> deterministic regex parser.
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
                slide_text = str(item.get("slide_text", "")).strip()
                key_points = [str(kp) for kp in item.get("key_points", []) if kp]
                # FIX: LLMs sometimes return a topic with empty slide_text but
                # with valid key_points (they assigned the slide content to an
                # earlier topic).  Backfill from key_points so note_generator
                # has something to write from.
                if not slide_text and key_points:
                    slide_text = "\n".join(f"- {kp}" for kp in key_points)
                    logger.warning(
                        "slide_analyzer: topic %r had empty slide_text - "
                        "backfilled from %d key_points", topic_name, len(key_points)
                    )
                all_topics.append(SlideTopic(
                    topic=topic_name,
                    slide_text=slide_text,
                    key_points=key_points,
                ))
        else:
            # Fallback for this chunk
            all_topics.extend(_deterministic_parse(chunk_text))

    if all_topics:
        all_topics = _deduplicate_topics(all_topics)
        logger.info("slide_analyzer: %d topics after deduplication (from %d chunks)",
                    len(all_topics), len(chunks))
        return all_topics

    logger.info("slide_analyzer: using deterministic fallback parser")
    topics = _deterministic_parse(slides_text)
    logger.info("slide_analyzer: extracted %d topics via fallback", len(topics))
    return topics


def _topic_similarity(a: str, b: str) -> float:
    """
    Word-overlap similarity between two topic names (0.0 to 1.0).
    Used to detect duplicate topics across PDF files.
    """
    stop = {"the", "a", "an", "of", "and", "in", "to", "for", "on", "with",
            "introduction", "intro", "overview", "basics", "part", "lecture",
            "distribution", "theorem", "method", "analysis", "process", "function"}
    def words(s):
        return {w for w in s.lower().replace("-", " ").split() if len(w) > 2 and w not in stop}
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _deduplicate_topics(topics: list) -> list:
    """
    Merge topic entries that refer to the same concept across multiple PDF files.

    Duplicates arise when multiple PDFs cover the same topic, or when the LLM
    uses slightly different names across chunks ("DFT" vs "Discrete Fourier Transform").

    Strategy:
      - Topics with name similarity >= 0.7 are merged into one entry.
      - Merged entry keeps the first occurrence name.
      - slide_text values are concatenated so ALL content is preserved.
      - key_points are deduplicated while preserving order.

    Result: no duplicate ## sections in the generated notes.
    """
    THRESHOLD = 0.5
    merged = []
    used = [False] * len(topics)

    for i, t in enumerate(topics):
        if used[i]:
            continue
        group = [t]
        used[i] = True
        for j in range(i + 1, len(topics)):
            if not used[j] and _topic_similarity(t.topic, topics[j].topic) >= THRESHOLD:
                group.append(topics[j])
                used[j] = True

        if len(group) == 1:
            merged.append(t)
        else:
            # Combine: use first topic name, merge all slide texts, dedup key_points
            combined_text = "\n\n".join(
                f"[{g.topic}]\n{g.slide_text}" if g.topic != group[0].topic else g.slide_text
                for g in group
            )
            seen_kp: set = set()
            combined_kp = []
            for g in group:
                for kp in g.key_points:
                    norm = kp.strip().lower()
                    if norm not in seen_kp:
                        seen_kp.add(norm)
                        combined_kp.append(kp.strip())

            logger.info(
                "dedup: merged %d topics under '%s' (%s)",
                len(group), group[0].topic,
                ", ".join(f"'{g.topic}'" for g in group[1:])
            )
            merged.append(SlideTopic(
                topic      = group[0].topic,
                slide_text = combined_text,
                key_points = combined_kp,
            ))

    return merged
