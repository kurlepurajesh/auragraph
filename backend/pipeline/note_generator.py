"""
pipeline/note_generator.py
──────────────────────────
Step 6 + Step 7 + Step 8 — Note Generation, Merging, Refinement.

For each lecture topic:
  • Slide content (verbatim from slide_analyzer)
  • Retrieved textbook context (from topic_retriever)
  → One GPT call per topic → structured Markdown section

Then:
  • Merge all sections into one document (Step 7)
  • Optional single refinement pass (Step 8)

LLM call budget (as required by spec):
  1  call for slide analysis        (slide_analyzer.py)
  N  calls for per-topic generation (this file)
  1  call for refinement            (this file, optional)

Fallback: if Azure is unavailable, builds notes from slide content alone
using deterministic templates — same quality as local_summarizer.py.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from pipeline.slide_analyzer import SlideTopic
from agents.latex_utils import fix_latex_delimiters

logger = logging.getLogger(__name__)


# ── Prompts ───────────────────────────────────────────────────────────────────

_NOTE_SYSTEM = """\
You are AuraGraph, an expert academic note writer for engineering students in India.
Your notes are read the night before an exam. Every sentence must earn its place.
"""

_NOTE_USER_TEMPLATE = """\
Generate structured study notes for ONE lecture topic.

TOPIC: {topic}

SLIDE CONTENT (primary — follow this exactly):
{slide_text}

TEXTBOOK CONTEXT (enrichment only — deepen the slide content, never add new topics):
{textbook_context}

TARGET PROFICIENCY: {proficiency}

════════════════════════════════
RULES (follow strictly)
════════════════════════════════
STRUCTURE:
• Start with exactly: ## {topic}
• Only add ### sub-headings if the topic genuinely has distinct sub-topics.
• End with: > 📝 **Exam Tip:** (one sentence, exam-specific)
• No preamble, no conclusion paragraphs.

CONTENT:
• Follow the SLIDE CONTENT as your primary source.
• Use TEXTBOOK CONTEXT only to clarify, add a missing definition, or add one example.
• NEVER introduce a concept that is not in the slides.

PROFICIENCY ADAPTATION:
BEGINNER:
  1. Plain-English sentence: "Simply put, X is …"
  2. One analogy in a > blockquote.
  3. Key formula(s) with **Where:** table (one line per symbol).
  4. Numbered steps if there is a process.

INTERMEDIATE:
  1. Formal definition.
  2. Intuition sentence linking formula to real meaning.
  3. Display LaTeX for every key formula; define symbols inline.
  4. Key conditions / edge cases as bullets.

ADVANCED:
  1. Formal definition with all conditions.
  2. Full derivation. Terse algebra. No commentary between steps.
  3. Validity / convergence conditions.
  4. Edge cases as bullets.
  5. One comparison with a related concept.

MATHEMATICS:
• ALL math in LaTeX. NEVER write "integral", "sigma", "omega" as English words.
• Inline: $expression$   Display (own line):
  $$
  formula here
  $$
• NEVER use \\[ \\] or \\( \\). ONLY $ and $$.
• NEVER wrap math in backtick code fences.

OUTPUT: Only the ## section. Nothing before it, nothing after the Exam Tip.
"""

_REFINEMENT_SYSTEM = """\
You are an expert academic editor.
Improve the clarity and readability of these study notes.
"""

_REFINEMENT_USER = """\
Below are draft study notes. Improve them according to these rules:

RULES:
• Do NOT add new topics or ## sections.
• Do NOT change the topic order or structure.
• Fix awkward phrasing, redundancy, and unclear explanations.
• Ensure all formulas use $...$ or $$ ... $$ LaTeX — never \\( \\) or \\[ \\].
• Ensure every ## section ends with > 📝 **Exam Tip:** ...
• Remove any preamble or conclusion text you find.
• Output ONLY the improved notes — no commentary.

NOTES:
{notes}
"""


# ── LLM availability + call helpers ──────────────────────────────────────────

def _azure_available() -> bool:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key  = os.environ.get("AZURE_OPENAI_API_KEY",  "")
    return bool(endpoint) and bool(api_key) and "mock" not in endpoint.lower()


def _groq_available() -> bool:
    key = os.environ.get("GROQ_API_KEY", "")
    return key not in ("", "your-groq-api-key-here")


async def _call_azure(
    system: str,
    user:   str,
    max_tokens: int = 2500,
) -> Optional[str]:
    """Azure OpenAI call via openai SDK. Returns text or None on failure."""
    if not _azure_available():
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
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": user}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning("note_generator Azure call failed: %s", e)
        return None


async def _call_groq(
    system: str,
    user:   str,
    max_tokens: int = 2500,
) -> Optional[str]:
    """Groq call via openai SDK. Returns text or None on failure."""
    if not _groq_available():
        return None
    try:
        from openai import OpenAI
        def _sync():
            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=os.environ.get("GROQ_API_KEY", ""),
            )
            model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user",   "content": user}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.warning("note_generator Groq call failed: %s", e)
        return None


# ── Per-topic generation ───────────────────────────────────────────────────

async def generate_topic_note(
    topic:            SlideTopic,
    textbook_context: str,
    proficiency:      str = "Intermediate",
) -> tuple[str, str]:
    """
    Generate one ## section for a single lecture topic.
    Returns (section_text, source) where source is 'azure' | 'groq' | 'local'.
    """
    if _azure_available():
        user = _NOTE_USER_TEMPLATE.format(
            topic=topic.topic,
            slide_text=topic.slide_text[:6_000],
            textbook_context=textbook_context[:4_000] if textbook_context else "(none)",
            proficiency=proficiency,
        )
        result = await _call_azure(_NOTE_SYSTEM, user, max_tokens=2500)
        if result:
            if not result.lstrip().startswith("##"):
                result = f"## {topic.topic}\n\n{result}"
            return fix_latex_delimiters(result), "azure"

    if _groq_available():
        user = _NOTE_USER_TEMPLATE.format(
            topic=topic.topic,
            slide_text=topic.slide_text[:5_000],
            textbook_context=textbook_context[:3_000] if textbook_context else "(none)",
            proficiency=proficiency,
        )
        result = await _call_groq(_NOTE_SYSTEM, user, max_tokens=2500)
        if result:
            if not result.lstrip().startswith("##"):
                result = f"## {topic.topic}\n\n{result}"
            return fix_latex_delimiters(result), "groq"

    # ── Deterministic fallback ─────────────────────────────────────────────────────
    return _build_fallback_section(topic, textbook_context, proficiency), "local"


def _build_fallback_section(
    topic:            SlideTopic,
    textbook_context: str,
    proficiency:      str,
) -> str:
    """
    Build a note section without LLM.
    Preserves all slide content and inlines a snippet of textbook context.
    """
    from agents.local_summarizer import _build_section, _extract_math_and_prose

    body = topic.slide_text
    # Strip slide boundary markers for the body
    import re
    body = re.sub(r'^---\s*Slide\s+\d+[^\n]*---\s*\n?', '', body, flags=re.MULTILINE).strip()
    enrichment = textbook_context[:300] if textbook_context else ""

    section = _build_section(topic.topic, body, enrichment, 8, proficiency)
    if section:
        return fix_latex_delimiters(section)

    # Absolute fallback: just wrap slide text
    return fix_latex_delimiters(f"## {topic.topic}\n\n{body}\n\n> 📝 **Exam Tip:** Review this concept carefully.")


# ── Merge + Refinement ─────────────────────────────────────────────────────

def merge_sections(sections: list[str]) -> str:
    """Concatenate all topic sections in order with clean spacing."""
    cleaned = []
    for s in sections:
        s = s.strip()
        if s:
            cleaned.append(s)
    return "\n\n".join(cleaned)


async def refine_notes(notes: str) -> str:
    """
    Single refinement pass to improve clarity (Step 8).
    Tries Azure first, then Groq. Skips if no LLM available or notes < 500 chars.
    Returns original notes on failure.
    """
    if len(notes) < 500:
        return notes

    user = _REFINEMENT_USER.format(notes=notes[:28_000])

    if _azure_available():
        refined = await _call_azure(_REFINEMENT_SYSTEM, user, max_tokens=8192)
        if refined and len(refined) > len(notes) * 0.3:
            return fix_latex_delimiters(refined)

    if _groq_available():
        refined = await _call_groq(_REFINEMENT_SYSTEM, user, max_tokens=8192)
        if refined and len(refined) > len(notes) * 0.3:
            return fix_latex_delimiters(refined)

    logger.info("Refinement produced short/empty output — keeping original")
    return notes


# ── Full pipeline orchestration ────────────────────────────────────────────

async def run_generation_pipeline(
    topics:           list[SlideTopic],
    topic_contexts:   dict[str, str],   # topic_name → textbook context string
    proficiency:      str = "Intermediate",
    refine:           bool = True,
) -> tuple[str, str]:
    """
    Run Step 6 (N topic calls) + Step 7 (merge) + Step 8 (refinement).

    Returns:
        Tuple of (merged_notes, source) where source is
        'azure' | 'groq' | 'local'.
    """
    if not topics:
        return "", "local"

    sections: list[str] = []
    topic_sources: list[str] = []
    for topic in topics:
        context = topic_contexts.get(topic.topic, "")
        logger.info("Generating note for topic: %s", topic.topic)
        section, topic_src = await generate_topic_note(topic, context, proficiency)
        sections.append(section)
        topic_sources.append(topic_src)

    merged = merge_sections(sections)

    # Determine source from what was actually used across all topic calls
    if "azure" in topic_sources:
        source = "azure"
    elif "groq" in topic_sources:
        source = "groq"
    else:
        source = "local"

    if refine and (_azure_available() or _groq_available()):
        logger.info("Running refinement pass on %d chars", len(merged))
        merged = await refine_notes(merged)

    return merged, source
