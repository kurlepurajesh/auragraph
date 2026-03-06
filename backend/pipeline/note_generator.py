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
import re
from typing import Optional

from pipeline.slide_analyzer import SlideTopic
from agents.latex_utils import fix_latex_delimiters

logger = logging.getLogger(__name__)


# ── Table repair ──────────────────────────────────────────────────────────────

def _fix_tables(text: str) -> str:
    """
    Repair common Groq/LLM table generation errors:
    1. Missing alignment row  (header row immediately followed by data row)
    2. Rows with inconsistent column counts — pad or trim to match header
    3. Strip accidental leading/trailing whitespace inside cells
    """
    import re
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect a pipe-table header row: starts and ends with |, has at least one |
        if re.match(r'^\s*\|.*\|\s*$', line) and '|' in line:
            # Count columns from header
            header_cells = [c.strip() for c in line.strip().strip('|').split('|')]
            ncols = len(header_cells)
            result.append(line)
            # Check if next non-empty line is already an alignment row
            j = i + 1
            if j < len(lines) and re.match(r'^\s*\|[\s|:\-]+\|\s*$', lines[j]):
                # Already has alignment row — just ensure column count matches
                align_cells = [c.strip() for c in lines[j].strip().strip('|').split('|')]
                if len(align_cells) != ncols:
                    # Rebuild alignment row
                    lines[j] = '| ' + ' | '.join(['---'] * ncols) + ' |'
                result.append(lines[j])
                i = j + 1
            else:
                # Insert missing alignment row
                result.append('| ' + ' | '.join(['---'] * ncols) + ' |')
                i += 1
            # Process data rows: normalise column count
            while i < len(lines):
                dline = lines[i]
                if not re.match(r'^\s*\|.*\|\s*$', dline):
                    break  # end of this table
                data_cells = [c.strip() for c in dline.strip().strip('|').split('|')]
                if len(data_cells) < ncols:
                    data_cells.extend([''] * (ncols - len(data_cells)))
                elif len(data_cells) > ncols:
                    data_cells = data_cells[:ncols]
                result.append('| ' + ' | '.join(data_cells) + ' |')
                i += 1
            continue
        result.append(line)
        i += 1
    return '\n'.join(result)


# ── Prompts ───────────────────────────────────────────────────────────────────

_NOTE_SYSTEM = """\
You are AuraGraph — India's sharpest AI exam coach writing study notes for engineering students.
Your notes are the LAST thing a student reads the night before their university exam.

Five laws you NEVER break:
① COMPLETE       — Every formula, definition, and algorithm from the slides must appear. Zero omissions.
② EXAM-SHARP     — Every ## section ends with the single most-tested fact or most common mistake.
③ WORKED EXAMPLE — For every formula or process, show ONE concise numerical or symbolic worked example.
④ MNEMONIC       — If there is a pattern students forget, give a 1-line memory trick.
⑤ HONEST         — If the slide is sparse, write what you know accurately. Never pad with filler.

Banned phrases (never write these): "delve", "explore", "It is important to note",
"In conclusion", "In this section", "Overview:", "As we can see", "Please note".
"""

_NOTE_USER_TEMPLATE = """\
Generate structured study notes for ONE lecture topic.

TOPIC: {topic}

KEY POINTS FROM SLIDES:
{key_points_block}

SLIDE CONTENT (primary source — follow this exactly):
{slide_text}

{textbook_instruction}

TARGET PROFICIENCY: {proficiency}

════════════════════════════════
MANDATORY RULES
════════════════════════════════
STRUCTURE:
• Start with exactly: ## {topic}
• Only add ### sub-headings if the topic genuinely has distinct sub-topics.
• After the core content, add a worked example block: ### 🔢 Worked Example
• If there is a rule or pattern students forget, add: > 💡 **Mnemonic:** ...
• End with: > 📝 **Exam Tip:** (the single most-tested fact or most common error)
• No preamble sentences. No conclusion paragraphs.

CONTENT:
• SLIDE CONTENT is your primary source — never drop a definition or formula found there.
• Use textbook context only to clarify a definition or add one supporting example.
• NEVER introduce a concept that is not in the slides.

WORKED EXAMPLE (mandatory for every section):
• Pick a concrete number or symbol. Show 2–4 steps. Keep it compact.
• Format:
  ### 🔢 Worked Example — [brief title]
  **Given:** ...
  **Find:** ...
  **Solution:** step-by-step

PROFICIENCY ADAPTATION:
BEGINNER:
  1. Plain-English sentence: "Simply put, X is …"
  2. One analogy in a > blockquote.
  3. Key formula(s) with a **Where:** pipe-table defining each symbol:
     | Symbol | Meaning |
     |--------|---------|
     | $F$ | output value |
  4. Numbered steps if there is a process.

INTERMEDIATE:
  1. Formal definition.
  2. Intuition sentence linking the formula to real physical meaning.
  3. Display LaTeX for every key formula; define symbols inline.
  4. Key conditions / edge cases as bullets.
  5. If multiple related formulas exist, show a comparison table:
     | Formula | When to use |
     |---------|-------------|

ADVANCED:
  1. Formal definition with all boundary conditions.
  2. Full derivation — terse algebra, no commentary between steps.
  3. Validity / convergence conditions.
  4. Edge cases as bullets.
  5. Comparison with a related concept:
     | Aspect | This concept | Related concept |
     |--------|--------------|----------------|

TABLES:
• Pipe-tables ONLY. Header row + alignment row (|---|---| with ≥ 3 dashes) + data rows.
• NEVER use HTML tables.
• Every | column | must have pipe characters on both outer edges.

MATHEMATICS:
• ALL math must be in LaTeX. NEVER write "integral", "sigma", "omega" as English words.
• Inline: $expression$
• Display (own line):
  $$
  formula here
  $$
• NEVER use \\[ \\] or \\( \\). ONLY $ and $$.
• NEVER wrap math in backtick code fences.

OUTPUT: Only the ## section. Nothing before ## {topic}. Nothing after the Exam Tip.
"""

_REFINEMENT_SYSTEM = """\
You are an expert academic editor improving engineering study notes.
Your job is to enhance clarity, completeness, and structure without removing content.
"""

_REFINEMENT_USER = """\
Below are draft study notes. Improve them strictly according to these rules:

RULES:
• Do NOT remove any ## sections or change their order.
• Do NOT shorten notes — if anything, add missing detail.
• Fix awkward phrasing, redundancy, and unclear explanations.
• Ensure all formulas use $...$ or $$ ... $$ LaTeX — never \\( \\) or \\[ \\].
• Ensure every ## section ends with > 📝 **Exam Tip:** ...
• Remove any preamble or conclusion text (e.g. "Here are your notes").
• Output ONLY the improved notes — no commentary, no labels.

NOTES:
{notes}
"""

# ── Textbook instruction builder ─────────────────────────────────────────────

def _textbook_instruction_block(textbook_context: str, max_chars: int = 5_000) -> str:
    """Build the textbook context block for the note generation prompt."""
    has_tb = bool(textbook_context) and textbook_context.strip() not in ("", "(none)")
    if has_tb:
        return (
            "TEXTBOOK CONTEXT (enrichment only — deepen slide content, never add new topics):\n"
            + textbook_context[:max_chars]
        )
    return (
        "TEXTBOOK CONTEXT: None provided.\n"
        "→ Generate SELF-CONTAINED notes from slides alone. Be thorough:\n"
        "  define every term used, show full derivations, and make the worked example"
        " doubly clear since the student has no other reference."
    )


# ── Post-processor ────────────────────────────────────────────────────────────

_PREAMBLE_RE = re.compile(
    r'^(?:here(?:\s+are|is)|sure[,!]?|certainly[,!]?|below|of course[,!]?'
    r'|the\s+following|these\s+are)\b.*?\n+',
    re.IGNORECASE | re.DOTALL,
)

def _post_process_section(text: str, topic: str) -> str:
    """
    Clean up a single generated ## section:
    1. Strip any LLM preamble before the ## heading
    2. Ensure the section starts with ## topic
    3. Ensure it ends with an Exam Tip blockquote
    """
    # 1. strip preamble lines before the ## heading
    lines = text.split('\n')
    start = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith('##'):
            start = i
            break
    text = '\n'.join(lines[start:]).strip()

    # 2. ensure heading present
    if not text.lstrip().startswith('##'):
        text = f'## {topic}\n\n{text}'

    # 3. ensure exam tip present at end
    if '📝' not in text and 'Exam Tip' not in text:
        text = text.rstrip() + f'\n\n> 📝 **Exam Tip:** Review the definition and key formula for {topic}.'

    return text.strip()

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
    # Build the key_points block for the prompt
    key_points_block = (
        "\n".join(f"- {kp}" for kp in topic.key_points)
        if topic.key_points else "(extracted from slide content below)"
    )

    if _azure_available():
        user = _NOTE_USER_TEMPLATE.format(
            topic=topic.topic,
            key_points_block=key_points_block,
            slide_text=topic.slide_text[:8_000],
            textbook_instruction=_textbook_instruction_block(textbook_context, 5_000),
            proficiency=proficiency,
        )
        result = await _call_azure(_NOTE_SYSTEM, user, max_tokens=3500)
        if result:
            result = _post_process_section(result, topic.topic)
            return fix_latex_delimiters(_fix_tables(result)), "azure"

    if _groq_available():
        user = _NOTE_USER_TEMPLATE.format(
            topic=topic.topic,
            key_points_block=key_points_block,
            slide_text=topic.slide_text[:6_000],
            textbook_instruction=_textbook_instruction_block(textbook_context, 4_000),
            proficiency=proficiency,
        )
        result = await _call_groq(_NOTE_SYSTEM, user, max_tokens=3000)
        if result:
            result = _post_process_section(result, topic.topic)
            return fix_latex_delimiters(_fix_tables(result)), "groq"

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
    from agents.local_summarizer import _build_section

    body = topic.slide_text
    # Strip slide/page boundary markers for the body
    body = re.sub(r'^---\s*(?:Slide|Page)\s+\d+[^\n]*---\s*\n?', '', body, flags=re.MULTILINE).strip()
    enrichment = textbook_context[:300] if textbook_context else ""

    section = _build_section(topic.topic, body, enrichment, 8, proficiency)
    if section:
        return fix_latex_delimiters(section)

    # Absolute fallback: just wrap slide text
    return fix_latex_delimiters(f"## {topic.topic}\n\n{body}\n\n> 📝 **Exam Tip:** Review the definition and key formula for {topic.topic}.")


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
    For large notes (>18k chars), Groq cannot reliably refine the full text
    without truncation, so refinement is skipped for Groq on large outputs.
    Returns original notes on failure.
    """
    if len(notes) < 500:
        return notes

    # Groq has tight output limits — skip refinement for large note sets
    # to avoid silently truncating 50% of the content
    groq_refine_ok = _groq_available() and len(notes) <= 18_000

    user = _REFINEMENT_USER.format(notes=notes[:28_000])

    if _azure_available():
        refined = await _call_azure(_REFINEMENT_SYSTEM, user, max_tokens=8192)
        if refined and len(refined) > len(notes) * 0.6:
            return fix_latex_delimiters(_fix_tables(refined))
        if refined:
            logger.info("Azure refinement output too short (%d vs %d) — keeping original", len(refined), len(notes))

    if groq_refine_ok:
        refined = await _call_groq(_REFINEMENT_SYSTEM, user, max_tokens=8192)
        if refined and len(refined) > len(notes) * 0.6:
            return fix_latex_delimiters(_fix_tables(refined))
        if refined:
            logger.info("Groq refinement output too short (%d vs %d) — keeping original", len(refined), len(notes))

    logger.info("Refinement skipped/failed — keeping original %d-char notes", len(notes))
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

    Topic notes are generated CONCURRENTLY (up to 4 at a time) to avoid
    making the student wait 30-50 seconds for a sequential loop.

    Returns:
        Tuple of (merged_notes, source) where source is
        'azure' | 'groq' | 'local'.
    """
    if not topics:
        return "", "local"

    # Semaphore: max 4 concurrent LLM calls (avoids Groq rate limits)
    sem = asyncio.Semaphore(4)

    async def _generate_with_sem(topic: SlideTopic) -> tuple[str, str]:
        async with sem:
            context = topic_contexts.get(topic.topic, "")
            logger.info("Generating note for topic: %s", topic.topic)
            return await generate_topic_note(topic, context, proficiency)

    # Generate all topics concurrently
    results = await asyncio.gather(*[_generate_with_sem(t) for t in topics])
    sections     = [r[0] for r in results]
    topic_sources = [r[1] for r in results]

    merged = merge_sections(sections)

    # Determine source from what was actually used across all topic calls
    if "azure" in topic_sources:
        source = "azure"
    elif "groq" in topic_sources:
        source = "groq"
    else:
        source = "local"

    if refine and (_azure_available() or _groq_available()):
        logger.info("Running refinement pass on %d chars (source=%s)", len(merged), source)
        merged = await refine_notes(merged)

    return merged, source
