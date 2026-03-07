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


# ── Safe template substitution ──────────────────────────────────────────────

def _safe_format(template: str, **kwargs) -> str:
    """
    Substitute named placeholders like {topic} in a template string WITHOUT
    using str.format(), which chokes on LaTeX curly-braces in the values
    (e.g. '{x^2}' raises KeyError: 'x^2').
    """
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


# -- Prompts ------------------------------------------------------------------

_NOTE_SYSTEM = """You are AuraGraph -- an AI study notes engine for engineering students.

YOUR ONLY JOB: Convert professor slides and lecture notes into study notes.

THE ONE RULE THAT OVERRIDES EVERYTHING ELSE:
Every single piece of content present in the input slides/notes MUST appear in the output.
Not a summary of it. Not a mention of it. The actual content -- every formula, every
definition, every algorithm step, every property, every condition, every exception,
every worked example, every edge case -- must be present in the generated notes.

Proficiency level NEVER controls what is included. It only controls HOW things are explained.
A concept present in the slides that is absent from the notes is always an error,
regardless of proficiency level.

ACCURACY RULE:
You are the ground truth for correctness. Before writing any formula, definition, or claim,
verify it against your knowledge. If the source has an error, write the correct version silently.
This covers:
  - Formula errors (wrong sign, wrong operator, missing factor, inverted fraction)
  - Incomplete definitions (e.g. "monotonic" without "strictly monotonic and differentiable")
  - Wrong theorem conditions or directions of implication
  - OCR artifacts (garbled math) -- reconstruct correct LaTeX from context

BANNED PHRASES (never write): "delve", "explore", "It is important to note",
"In conclusion", "In this section", "As we can see", "Please note", "Overview:".
"""

# Per-proficiency instruction blocks injected into the user prompt

_PROFICIENCY_BEGINNER = """PROFICIENCY: BEGINNER

Your goal: produce notes that a student encountering this topic for the first time
can fully understand without any outside help.

HOW TO HANDLE EVERY CONCEPT FROM THE SLIDES:
  1. Start with a plain-English sentence: "Simply put, X means..."
  2. Follow with a real-world analogy in a > blockquote to make it concrete.
  3. State the formal definition after the analogy -- never before.
  4. For EVERY formula:
       a. Write the formula in display LaTeX ($$...$$)
       b. Follow with a symbol table:
          | Symbol | What it means | Typical units/range |
          |--------|---------------|---------------------|
       c. Walk through it in plain English: "This says that X equals Y times Z, where..."
       d. Work a FULLY SOLVED numerical example -- show every arithmetic step, no skipping.
  5. For every algorithm or process: write it as a numbered step-by-step procedure.
     Each step gets one plain-English sentence of explanation.
  6. For every condition or exception: explain WHY it exists.
     ("This condition is needed because without it, X would fail/blow up/be undefined...")
  7. For every edge case: explain what it means and when it arises.

DEPTH: Go deep. A beginner needs MORE explanation per concept, not less.
If something could be confusing, add a sentence. Never assume prior knowledge.
Leave nothing assumed.

LENGTH: Beginner notes are the longest of the three levels. More explanation,
more examples, more analogies. Never truncate or skip anything to save space.
"""

_PROFICIENCY_INTERMEDIATE = """PROFICIENCY: INTERMEDIATE

The student knows the basics. Your goal is to bridge surface understanding and
real exam-level fluency.

HOW TO HANDLE EVERY CONCEPT FROM THE SLIDES:
  1. State the formal definition directly.
  2. For EVERY formula:
       a. Write it in display LaTeX ($$...$$) with symbols defined inline.
       b. Give one sentence of intuition: what is the formula really saying,
          not just what it computes.
       c. Show a worked example that reveals non-obvious behaviour -- use numbers
          or symbolic values that make the formula's meaning clear.
  3. For any concept commonly misunderstood or confused with something else:
     write a focused explanation of the correct mental model.
  4. For any concept where the slides only give a brief mention or glance:
     fill in the gap with a precise explanation so the student has no holes.
  5. Where the textbook has a cleaner analogy or a better way of seeing something
     that was rushed over in the slides: bring it in. Mark it [Textbook] inline.
  6. Show a comparison table wherever related formulas or concepts are easily confused:
     | Concept | When to use | Key difference |
     |---------|-------------|----------------|
  7. For every condition, exception, and edge case: state it and explain
     the consequence of violating or ignoring it.

DEPTH: Full coverage, no shortcuts. Explanations assume mathematical maturity
and skip trivial steps, but never skip important ones.

LENGTH: Comprehensive. Every topic in the slides gets thorough treatment.
"""

_PROFICIENCY_ADVANCED = """PROFICIENCY: ADVANCED

The student is exam-ready on the basics. Your goal is to push them to genuine mastery.

HOW TO HANDLE EVERY CONCEPT FROM THE SLIDES:
  1. All fundamental definitions and basic properties: state them concisely.
     One or two sentences. No hand-holding.
  2. For EVERY formula:
       a. Write it in display LaTeX.
       b. If it has a non-trivial derivation: show the full derivation.
          Terse algebra, no commentary between steps. Skip only trivially
          obvious algebraic rearrangements.
       c. State ALL conditions for validity: convergence, domain restrictions,
          boundary conditions, underlying assumptions. If the slides omit a
          mathematically necessary condition, add it.
  3. For every important concept: go one level deeper.
     Bring in the stronger theorem, the generalisation, the connection to a
     related concept, or the precise condition under which it breaks down.
     Use the textbook as the source for this deeper material.
  4. Replace trivial textbook examples with HARD problems:
       - Problems requiring two or more concepts from the slides combined.
       - Non-standard parameter values that reveal edge-case behaviour.
       - Problems that look like one type but require insight to recognise as another.
     Show full solutions with every step and a note on the key insight.
  5. For every edge case and exception: explain the mathematical reason it arises,
     not just the fact that it exists.
  6. Where two concepts are related or one generalises the other, add a precise
     comparison:
     | Aspect | This | Generalisation / Related |
     |--------|------|--------------------------|

DEPTH: Every concept from the slides gets full advanced treatment. Basic things
get one sentence; non-trivial things get derivations, hard examples, and deeper theory.

LENGTH: As long as needed. Do not truncate derivations or problem solutions.
"""

_NOTE_USER_TEMPLATE = """Generate study notes for the following lecture topic.

TOPIC: {topic}

KEY POINTS FROM SLIDES (every single one MUST appear in your output):
{key_points_block}

SLIDE / LECTURE NOTES CONTENT (primary source -- reproduce every item):
{slide_text}

{textbook_instruction}

{proficiency_block}

NON-NEGOTIABLE COVERAGE RULES (these apply at ALL proficiency levels, no exceptions)
=====================================================================================
Before writing anything, read the SLIDE CONTENT above and list internally:
  - every formula and equation
  - every definition
  - every algorithm, procedure, or process
  - every theorem, lemma, or property
  - every condition, constraint, and edge case
  - every exception and special case
  - every example worked through in the slides

Every single item on that list MUST appear in your output.
No exceptions. Not for length. Not for proficiency level.
A concept present in the slides that does not appear in the output is an error.

STRUCTURE
=========
  - Start with: ## {topic}
  - Use ### sub-headings whenever the topic has genuinely distinct sub-topics.
  - End the section with:
      > Exam Tip: [the single most-tested fact or most common exam mistake for this topic]

MATHEMATICS
===========
  - ALL math in LaTeX. Never write "integral", "sigma", "omega", "delta" as English words.
  - Inline math: $expression$
  - Display math: $$
    formula
    $$
  - NEVER use \\\\( \\\\) or \\\\[ \\\\]. Only $ and $$.
  - OCR garbled math: reconstruct the correct LaTeX from your knowledge of the topic.

TABLES
======
  - Pipe-tables only: header row + |---|---| alignment row + data rows.
  - Never use HTML tables.

OUTPUT: Start immediately with ## {topic}. End with the Exam Tip. Nothing before or after.
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
• Remove any preamble or conclusion text (e.g. "Here are your notes").• Do NOT add new topics that were not already present.• Output ONLY the improved notes — no commentary, no labels.

NOTES:
{notes}
"""

# ── Post-generation self-verification prompts ─────────────────────────────────

_VERIFY_NOTES_SYSTEM = """\
You are a senior engineering professor and fact-checker.
You have been given AI-generated study notes. Your ONLY job is to find and
silently fix factual errors — do not change anything that is already correct.

You are the ground truth. Your own knowledge overrides whatever the notes say.

CHECK every single claim against your knowledge:
  FORMULAS        — sign, operator (+/−/×/÷), exponent, argument, fraction orientation,
                    missing factors, extra factors.
                    Common LLM error: using division where multiplication is required,
                    e.g.  f_Y(y) = f_X(f⁻¹(y)) / |...|   →  must be  × |...|
  DEFINITIONS     — are all conditions present? (e.g. "monotonic" → "strictly monotonic
                    and differentiable"; "linear" → "linear and time-invariant")
  THEOREM STATEMENTS — direction of implication correct? equality vs inequality correct?
                    all hypotheses listed?
  CONCEPTUAL CLAIMS — cause/effect, direction, units, domains, convergence conditions.
  WORKED EXAMPLES — re-run every calculation. If the answer or any step is wrong, fix it.

RULES:
  • Fix errors silently — do NOT say "the original notes said X" or "I corrected".
  • Do NOT remove any ## sections, alter the order, or shorten any section.
  • Do NOT change correct content.
  • Ensure every formula remains in valid LaTeX ($...$ or $$...$$).
  • Output ONLY the corrected notes — no preamble, no commentary, no labels.

If no errors are found, output the notes unchanged.
"""

_VERIFY_NOTES_USER = """\
These are AI-generated study notes. Fact-check every formula, definition,
theorem statement, conceptual claim, and worked example against your knowledge.
Fix all errors silently. Return the complete corrected notes.

NOTES:
{notes}
"""

# ── Textbook instruction builder ─────────────────────────────────────────────

def _resolve_proficiency_block(proficiency: str) -> str:
    """
    Map a proficiency string to the matching instruction block.
    Accepted values (case-insensitive):
      Beginner / Foundations / Basic / Foundation
      Intermediate / Practitioner / Medium
      Advanced / Expert
    Falls back to Intermediate for unknown values.
    """
    p = proficiency.strip().lower()
    if p in ("beginner", "foundations", "foundation", "basic"):
        return _PROFICIENCY_BEGINNER
    if p in ("advanced", "expert"):
        return _PROFICIENCY_ADVANCED
    # default: intermediate
    return _PROFICIENCY_INTERMEDIATE


def _textbook_instruction_block(textbook_context: str, max_chars: int = 7_000) -> str:
    """Build the textbook context block for the note generation prompt."""
    has_tb = bool(textbook_context) and textbook_context.strip() not in ("", "(none)")
    if has_tb:
        return (
            "TEXTBOOK CONTEXT (use this aggressively — it is a high-quality academic source):\n"
            + textbook_context[:max_chars]
            + "\n\n"
            "TEXTBOOK USAGE RULES:\n"
            "• Pull precise definitions, full theorem statements, and complete proofs directly from the textbook.\n"
            "• If the textbook has a worked example that matches the topic, reproduce or adapt it — cite [Textbook] inline.\n"
            "• If the textbook shows a derivation, include it step-by-step in the notes.\n"
            "• Prefer the textbook's notation when it is cleaner than the slide notation.\n"
            "• Use textbook chapter/section headings as sub-heading hints where relevant.\n"
            "• Do NOT introduce topics that appear ONLY in the textbook but NOT in the slides."
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
    # FIX (round 4): mirror main.py — also reject "placeholder" endpoints/keys
    return (
        bool(endpoint) and bool(api_key)
        and "mock"        not in endpoint.lower()
        and "placeholder" not in endpoint.lower()
        and "placeholder" not in api_key.lower()
    )


def _groq_available() -> bool:
    key = os.environ.get("GROQ_API_KEY", "")
    return key not in ("", "your-groq-api-key-here")


async def _call_azure(
    system: str,
    user:   str,
    max_tokens: int = 3000,
) -> Optional[str]:
    """
    Azure OpenAI call via httpx async client (true async — no thread pool).
    FIX C1: was asyncio.to_thread(_sync) which blocked thread pool under load.
    Includes one 429 retry with Retry-After back-off.
    If finish_reason=length (output truncated), retries once with the hard ceiling (14,000).
    """
    if not _azure_available():
        return None
    try:
        import httpx
        endpoint   = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        api_key    = os.environ.get("AZURE_OPENAI_API_KEY",  "")
        api_ver    = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_ver}"
        headers = {"api-key": api_key, "Content-Type": "application/json"}

        # First attempt with requested budget; second attempt (if truncated) with hard ceiling
        for attempt_tokens in [max_tokens, 14_000]:
            payload = {
                "messages":   [{"role": "system", "content": system},
                               {"role": "user",   "content": user}],
                "max_tokens": attempt_tokens,
                "temperature": 0.3,
            }
            for rate_attempt in range(2):
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 429 and rate_attempt == 0:
                    wait = int(resp.headers.get("Retry-After", "10"))
                    logger.warning("note_generator Azure 429 — retrying in %d s", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data   = resp.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") == "length":
                    if attempt_tokens < 14_000:
                        logger.warning(
                            "note_generator Azure: output truncated at %d tokens — "
                            "retrying with hard ceiling 14,000", attempt_tokens
                        )
                        break   # break inner rate-retry loop → outer loop increases tokens
                    else:
                        logger.warning(
                            "note_generator Azure: output still truncated at hard ceiling "
                            "14,000 tokens — returning partial result"
                        )
                return choice["message"]["content"].strip()
    except Exception as e:
        logger.warning("note_generator Azure async call failed: %s", e)
    return None


async def _call_groq(
    system: str,
    user:   str,
    max_tokens: int = 2500,
) -> Optional[str]:
    """
    Groq call via httpx async client (true async — no thread pool).
    FIX C1: was asyncio.to_thread(_sync) which blocked thread pool under load.
    Includes one 429 retry with Retry-After back-off.
    If finish_reason=length (output truncated), retries once with hard ceiling (7,500).
    """
    if not _groq_available():
        return None
    try:
        import httpx
        api_key = os.environ.get("GROQ_API_KEY", "")
        model   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        for attempt_tokens in [max_tokens, 7_500]:
            payload = {
                "model":       model,
                "messages":    [{"role": "system", "content": system},
                                {"role": "user",   "content": user}],
                "max_tokens":  attempt_tokens,
                "temperature": 0.3,
            }
            for rate_attempt in range(2):
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        json=payload, headers=headers,
                    )
                if resp.status_code == 429 and rate_attempt == 0:
                    wait = int(resp.headers.get("Retry-After", "6"))
                    logger.warning("note_generator Groq 429 — retrying in %d s", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data   = resp.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") == "length":
                    if attempt_tokens < 7_500:
                        logger.warning(
                            "note_generator Groq: output truncated at %d tokens — "
                            "retrying with hard ceiling 7,500", attempt_tokens
                        )
                        break   # break inner rate-retry loop → outer loop increases tokens
                    else:
                        logger.warning(
                            "note_generator Groq: output still truncated at hard ceiling "
                            "7,500 tokens — returning partial result"
                        )
                return choice["message"]["content"].strip()
    except Exception as e:
        logger.warning("note_generator Groq async call failed: %s", e)
    return None


# ── Per-topic generation ───────────────────────────────────────────────────

def _budget_for_topic(slide_text: str, provider: str) -> int:
    """
    Dynamically scale max_tokens based on how dense the slide content is.

    The rule of thumb: 1 char of slide content → ~1.2 chars of notes (explanations,
    worked examples, and LaTeX expand the content). Then add a fixed overhead for
    the Exam Tip, Mnemonic, and Worked Example blocks (~600 tokens).

    Hard ceilings are set by provider API limits:
      Azure GPT-4o  — 16,384 output tokens  (we cap at 14,000 to leave headroom)
      Groq llama-3  —  8,192 output tokens  (we cap at  7,500 to leave headroom)
    """
    # Estimate output chars needed ≈ 1.2× input chars + 2400 overhead chars
    estimated_output_chars = int(len(slide_text) * 1.2) + 2400
    # Convert chars → tokens (≈ 4 chars per token)
    estimated_tokens = estimated_output_chars // 4

    if provider == "azure":
        # Azure GPT-4o supports 16,384 output tokens; cap conservatively at 14,000
        return max(3000, min(estimated_tokens, 14_000))
    else:
        # Groq llama-3 supports 8,192 output tokens; cap at 7,500
        return max(2500, min(estimated_tokens, 7_500))


# ── Sub-chunk sizes (chars of slide_text per LLM call) ───────────────────────
# These are tuned so each call generates thorough notes without hitting output
# token limits.  The merge call later combines sub-drafts into one coherent section.
_SUBCHUNK_AZURE = 4_000   # ~1000 tokens input → ~1500 tokens output per sub-chunk
_SUBCHUNK_GROQ  = 3_000   # Groq is tighter; smaller chunks = less risk of truncation

# A topic is only split when slide_text exceeds this size.
# Below this threshold it's handled as one call (no merge overhead).
_SPLIT_THRESHOLD = 4_500


def _split_slide_text(slide_text: str, chunk_size: int) -> list[str]:
    """
    Split slide_text at slide/page boundary markers so we never cut mid-slide.
    Falls back to splitting at blank lines if no markers exist.
    """
    # Try to split on explicit slide markers: "--- Slide N ---" or "=== PAGE N ==="
    marker_re = re.compile(r'(?=^(?:---|\s*={3,})\s*(?:Slide|Page)\s+\d+', re.MULTILINE | re.IGNORECASE)
    parts = marker_re.split(slide_text)
    if len(parts) <= 1:
        # No slide markers — split on double newlines (paragraph boundaries)
        parts = re.split(r'\n{2,}', slide_text)

    chunks: list[str] = []
    buf = ""
    for part in parts:
        if buf and len(buf) + len(part) > chunk_size:
            if buf.strip():
                chunks.append(buf.strip())
            buf = part
        else:
            buf = buf + ("\n\n" if buf else "") + part
    if buf.strip():
        chunks.append(buf.strip())

    return chunks if chunks else [slide_text]


# Sub-chunk generation prompt — focused: cover THIS chunk exhaustively, no intro/conclusion
_SUBCHUNK_SYSTEM = """\
You are AuraGraph — India's sharpest AI exam coach writing a PARTIAL DRAFT of study notes.
You are writing notes for ONE chunk of slides that is part of a larger topic.

YOUR ONLY JOB: Extract and explain EVERY piece of content in the slide chunk below.
Do NOT write an introduction, conclusion, exam tip, or mnemonic — those go in the final merge.
Do NOT skip anything — formulas, definitions, algorithms, properties, examples — all of it.

Laws you NEVER break:
- Every formula, definition, and algorithm from this chunk MUST appear.
- All math in LaTeX ($...$ inline, $$...$$ display). Never write "integral", "sigma" as English.
- If the source has OCR artifacts or garbled math, reconstruct the correct LaTeX.
- Write in clear prose with ### sub-headings where the chunk has distinct sub-topics.
- No preamble ("Here are the notes..."). Start immediately with content.
"""

_SUBCHUNK_USER = """\
TOPIC (overall): {topic}
CHUNK NUMBER: {chunk_num} of {total_chunks}

SLIDE CONTENT FOR THIS CHUNK:
{slide_text}

{textbook_instruction}

{proficiency_block}

Write exhaustive notes covering EVERY item in this chunk. Use ### sub-headings freely.
No introduction, no conclusion, no exam tip -- just thorough content coverage.
Output ONLY the notes content. Nothing else.
"""

# Merge prompt -- takes N sub-drafts and produces one polished ## section
_MERGE_SYSTEM = """\
You are AuraGraph -- assembling partial note drafts into ONE polished study notes section.

You will receive multiple DRAFT CHUNKS covering different slides for the same topic,
plus a PROFICIENCY BLOCK that defines exactly how to explain everything.

Your job: combine all drafts into one coherent ## section, following the proficiency instructions.

NON-NEGOTIABLE LAWS:
1. ZERO OMISSIONS -- every formula, definition, algorithm, property, condition,
   exception, and example from ALL drafts MUST appear in the output.
   Do not drop anything. Do not summarise away a concept.
2. NO DUPLICATION -- if the same concept appears in multiple drafts, merge it cleanly.
3. PROFICIENCY -- apply the proficiency instructions to determine HOW each concept
   is explained. Coverage is fixed; depth and style are what the proficiency controls.
4. STRUCTURE -- one ## section with ### sub-headings where needed.
   End with: > Exam Tip: [most-tested fact or most common mistake]
5. ALL MATH in LaTeX ($...$ inline, $$...$$ display). Never use English words for symbols.
6. Start immediately with ## [topic]. Nothing before it. Nothing after the Exam Tip.
"""

_MERGE_USER = """\
TOPIC: {topic}

{proficiency_block}

DRAFT CHUNKS ({n} total) -- combine these into one complete ## section:
{drafts_block}

TEXTBOOK CONTEXT (use to enrich explanations per the proficiency level above):
{textbook_context}

NON-NEGOTIABLE: Every formula, definition, algorithm, condition, exception, and example
from ALL draft chunks MUST appear in your output. Do not drop anything.

Output ONLY the complete ## {topic} section. Start with ## {topic}. End with the Exam Tip.
"""


async def _generate_subchunk(
    topic:       str,
    chunk_text:  str,
    chunk_num:   int,
    total:       int,
    textbook_instruction: str,
    proficiency: str,
    provider:    str,
    api_sem:     asyncio.Semaphore | None = None,
) -> str | None:
    """Generate notes for one sub-chunk of a topic's slides."""
    user = _safe_format(
        _SUBCHUNK_USER,
        topic=topic,
        chunk_num=str(chunk_num),
        total_chunks=str(total),
        slide_text=chunk_text,
        textbook_instruction=textbook_instruction,
        proficiency_block=_resolve_proficiency_block(proficiency),
    )
    tokens = _budget_for_topic(chunk_text, provider)
    async def _call():
        if provider == "azure":
            return await _call_azure(_SUBCHUNK_SYSTEM, user, max_tokens=tokens)
        else:
            return await _call_groq(_SUBCHUNK_SYSTEM, user, max_tokens=tokens)
    if api_sem:
        async with api_sem:
            return await _call()
    return await _call()


async def _merge_drafts(
    topic:            str,
    drafts:           list[str],
    textbook_context: str,
    proficiency:      str,
    provider:         str,
    api_sem:          asyncio.Semaphore | None = None,
) -> str | None:
    """Merge N sub-chunk drafts into one polished ## section."""
    drafts_block = "\n\n".join(
        f"=== DRAFT {i+1} ===\n{d}" for i, d in enumerate(drafts)
    )
    user = _safe_format(
        _MERGE_USER,
        topic=topic,
        proficiency_block=_resolve_proficiency_block(proficiency),
        n=str(len(drafts)),
        drafts_block=drafts_block,
        textbook_context=textbook_context[:6_000] if textbook_context else "(none)",
    )
    total_draft_chars = sum(len(d) for d in drafts)
    tokens = _budget_for_topic(" " * total_draft_chars, provider)
    system = _MERGE_SYSTEM.replace("{topic}", topic)
    async def _call():
        if provider == "azure":
            return await _call_azure(system, user, max_tokens=tokens)
        else:
            return await _call_groq(system, user, max_tokens=tokens)
    if api_sem:
        async with api_sem:
            return await _call()
    return await _call()


async def generate_topic_note(
    topic:            SlideTopic,
    textbook_context: str,
    proficiency:      str = "Practitioner",
    api_sem:          asyncio.Semaphore | None = None,
) -> tuple[str, str]:
    """
    Generate one ## section for a single lecture topic.
    Returns (section_text, source) where source is 'azure' | 'groq' | 'local'.

    Architecture:
      - If slide_text <= _SPLIT_THRESHOLD: single LLM call (cheap, fast)
      - If slide_text > _SPLIT_THRESHOLD:
          1. Split slide_text into sub-chunks at slide boundaries
          2. Generate notes for each sub-chunk in parallel
          3. Merge all sub-chunk drafts into one polished section
        This guarantees EVERY slide's content appears in the final notes,
        regardless of how dense the topic is.
    """
    key_points_block = (
        "\n".join(f"- {kp}" for kp in topic.key_points)
        if topic.key_points else "(extracted from slide content below)"
    )

    # ── Determine provider ────────────────────────────────────────────────────
    provider = "azure" if _azure_available() else ("groq" if _groq_available() else None)
    if provider is None:
        return _build_fallback_section(topic, textbook_context, proficiency), "local"

    chunk_size   = _SUBCHUNK_AZURE if provider == "azure" else _SUBCHUNK_GROQ
    tb_per_chunk = 4_000            if provider == "azure" else 3_000

    # ── Short topic: single call path (no split overhead) ────────────────────
    if len(topic.slide_text) <= _SPLIT_THRESHOLD:
        tb_instr = _textbook_instruction_block(textbook_context, tb_per_chunk)
        user = _safe_format(
            _NOTE_USER_TEMPLATE,
            topic=topic.topic,
            key_points_block=key_points_block,
            slide_text=topic.slide_text,
            textbook_instruction=tb_instr,
            proficiency_block=_resolve_proficiency_block(proficiency),
        )
        tokens = _budget_for_topic(topic.slide_text, provider)
        async def _single_call():
            if provider == "azure":
                return await _call_azure(_NOTE_SYSTEM, user, max_tokens=tokens)
            return await _call_groq(_NOTE_SYSTEM, user, max_tokens=tokens)
        if api_sem:
            async with api_sem:
                result = await _single_call()
        else:
            result = await _single_call()
        if result:
            result = _post_process_section(result, topic.topic)
            return fix_latex_delimiters(_fix_tables(result)), provider
        return _build_fallback_section(topic, textbook_context, proficiency), "local"

    # ── Long topic: split → parallel generate → merge ────────────────────────
    sub_chunks = _split_slide_text(topic.slide_text, chunk_size)
    logger.info(
        "generate_topic_note: '%s' split into %d sub-chunks (%d chars total)",
        topic.topic, len(sub_chunks), len(topic.slide_text)
    )

    tb_instr_full  = _textbook_instruction_block(textbook_context, tb_per_chunk)
    tb_instr_brief = "TEXTBOOK CONTEXT: (provided to first chunk — focus on slide content here)"

    # Generate all sub-chunks concurrently (each call is throttled by api_sem)
    tasks = [
        _generate_subchunk(
            topic        = topic.topic,
            chunk_text   = chunk,
            chunk_num    = i + 1,
            total        = len(sub_chunks),
            textbook_instruction = tb_instr_full if i == 0 else tb_instr_brief,
            proficiency  = proficiency,
            provider     = provider,
            api_sem      = api_sem,
        )
        for i, chunk in enumerate(sub_chunks)
    ]
    drafts_raw = await asyncio.gather(*tasks)

    drafts = [d for d in drafts_raw if d and len(d.strip()) > 50]
    logger.info(
        "generate_topic_note: '%s' — %d/%d sub-chunks succeeded",
        topic.topic, len(drafts), len(sub_chunks)
    )

    if not drafts:
        logger.warning("generate_topic_note: all sub-chunks failed for '%s' — using fallback", topic.topic)
        return _build_fallback_section(topic, textbook_context, proficiency), "local"

    if len(drafts) == 1:
        result = _post_process_section(drafts[0], topic.topic)
        return fix_latex_delimiters(_fix_tables(result)), provider

    # Merge all drafts into one polished section
    merged = await _merge_drafts(topic.topic, drafts, textbook_context, proficiency, provider, api_sem=api_sem)
    if merged and len(merged.strip()) > 100:
        merged = _post_process_section(merged, topic.topic)
        return fix_latex_delimiters(_fix_tables(merged)), provider

    # Merge failed — concatenate drafts directly and post-process
    logger.warning("generate_topic_note: merge failed for '%s' — concatenating drafts", topic.topic)
    combined = f"## {topic.topic}\n\n" + "\n\n".join(drafts)
    combined = _post_process_section(combined, topic.topic)
    return fix_latex_delimiters(_fix_tables(combined)), provider


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


# ── Section-chunked LLM pass ─────────────────────────────────────────────────
# Used by both refine_notes and verify_notes so that large note sets
# (170k chars for 25 topics) are processed section-by-section instead of
# being silently truncated at 28 000 chars.

_CHUNK_BUDGET = 25_000   # chars per batch — well within Azure 128k context


def _split_into_section_batches(notes: str, budget: int = _CHUNK_BUDGET) -> list[str]:
    """Split notes on '## ' headings and group sections into budget-sized batches."""
    sections = re.split(r'(?m)(?=^## )', notes)
    batches, buf = [], ""
    for sec in sections:
        if buf and len(buf) + len(sec) > budget:
            batches.append(buf)
            buf = sec
        else:
            buf += sec
    if buf:
        batches.append(buf)
    return batches or [notes]


def _sections_ok(result: str, batch: str, batch_section_count: int, label: str, batch_num: int, total_batches: int) -> bool:
    """
    Validate that an LLM result for a batch is acceptable:
    - not shorter than 30% of the original batch
    - contains at least as many ## headings as the original batch
    """
    if len(result) < len(batch) * 0.3:
        return False
    if batch_section_count > 0:
        result_sections = len(re.findall(r'^## ', result, re.MULTILINE))
        if result_sections < batch_section_count:
            logger.warning(
                "%s batch %d/%d: LLM dropped %d/%d sections — keeping original",
                label, batch_num, total_batches,
                batch_section_count - result_sections, batch_section_count,
            )
            return False
    return True


async def _apply_llm_in_chunks(
    notes:  str,
    system: str,
    user_template: str,
    min_len: int = 500,
    label:  str = "pass",
) -> str:
    """
    Run an LLM pass (refinement or verification) section-by-section so that
    no content is dropped when notes exceed the 28 k char prompt budget.
    Azure is preferred; Groq is used only for batches ≤ 12 k chars.
    Returns the original notes if all batches fail.
    """
    if len(notes) < min_len:
        return notes

    batches = _split_into_section_batches(notes)
    logger.info("%s: %d chars → %d batch(es)", label, len(notes), len(batches))

    refined_batches: list[str] = []
    changed = False

    for i, batch in enumerate(batches):
        user = _safe_format(user_template, notes=batch)
        result: str | None = None
        batch_section_count = len(re.findall(r'^## ', batch, re.MULTILINE))

        if _azure_available():
            result = await _call_azure(system, user, max_tokens=16000)
            if result and not _sections_ok(result, batch, batch_section_count, label, i+1, len(batches)):
                logger.info("%s batch %d/%d: Azure output rejected — keeping original", label, i+1, len(batches))
                result = None

        if result is None and _groq_available() and len(batch) <= 12_000:
            result = await _call_groq(system, user, max_tokens=8192)
            if result and not _sections_ok(result, batch, batch_section_count, label, i+1, len(batches)):
                logger.info("%s batch %d/%d: Groq output rejected — keeping original", label, i+1, len(batches))
                result = None

        if result:
            refined_batches.append(fix_latex_delimiters(_fix_tables(result)))
            changed = True
        else:
            refined_batches.append(batch)  # keep original batch on failure

    if not changed:
        logger.info("%s: all batches failed — keeping original %d-char notes", label, len(notes))
        return notes

    return "\n\n".join(refined_batches)


async def refine_notes(notes: str) -> str:
    """
    Single refinement pass to improve clarity (Step 8).
    Processes notes section-by-section to avoid truncating large note sets.
    Returns original notes on failure.
    """
    return await _apply_llm_in_chunks(
        notes, _REFINEMENT_SYSTEM, _REFINEMENT_USER, min_len=500, label="refinement"
    )


# ── Post-generation fact-verification pass ────────────────────────────────────

async def verify_notes(notes: str) -> str:
    """
    Step 9 — Self-verification pass.

    Processes notes section-by-section (see _apply_llm_in_chunks) so that
    the full note set is fact-checked even for large (170k char) outputs.
    Returns original notes untouched on any failure.
    """
    return await _apply_llm_in_chunks(
        notes, _VERIFY_NOTES_SYSTEM, _VERIFY_NOTES_USER, min_len=500, label="verification"
    )


# ── Full pipeline orchestration ────────────────────────────────────────────

async def run_generation_pipeline(
    topics:           list[SlideTopic],
    topic_contexts:   dict[str, str],   # topic_name → textbook context string
    proficiency:      str = "Practitioner",
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

    # Filter out metadata/cover topics that have NO real teaching content (slide_text is empty or near-empty)
    # Only skip topics where the topic name is a metadata keyword AND the slide has no usable content.
    # Do NOT skip topics just because their name contains "overview" or "introduction" — those may have content.
    _HARD_SKIP_RE = re.compile(
        r'^(table of contents|references|bibliography|acknowledgement|acknowledgements|'
        r'thank you|q&a|title page|cover page|about this course)$',
        re.I,
    )
    def _should_skip(t: SlideTopic) -> bool:
        # Always skip hard metadata
        if _HARD_SKIP_RE.match(t.topic.strip()):
            return True
        # Skip if topic name is a metadata keyword AND slide has no real content (< 60 chars)
        _SOFT_SKIP = re.compile(r'\b(agenda|outline|questions|learning objectives|lecture overview|course overview|course introduction)\b', re.I)
        if _SOFT_SKIP.search(t.topic) and len(t.slide_text.strip()) < 60:
            return True
        return False

    topics = [t for t in topics if not _should_skip(t)]
    if not topics:
        return "", "local"

    # Concurrency control: every individual LLM call (sub-chunks + merges) is
    # throttled by this semaphore. This is more precise than wrapping entire topics
    # since a long topic may now make 3-5 LLM calls internally.
    _concurrency = int(os.environ.get("LLM_CONCURRENCY", "3"))
    _api_sem = asyncio.Semaphore(_concurrency)

    async def _generate_with_sem(topic: SlideTopic) -> tuple[str, str]:
        # Inject the semaphore into the topic note generator via a closure.
        # generate_topic_note passes it down to _generate_subchunk and _merge_drafts.
        context = topic_contexts.get(topic.topic, "")
        logger.info("Generating note for topic: %s", topic.topic)
        return await generate_topic_note(topic, context, proficiency, api_sem=_api_sem)

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

    # Refinement pass: improves clarity but is not essential for correctness.
    # Skip it when notes are very large (> 80k chars) -- the sub-chunk architecture
    # already produces well-structured notes, and refinement on 100+ topics would
    # add dozens of extra LLM calls without meaningful quality gain.
    _REFINE_CHAR_LIMIT = 80_000
    if refine and len(merged) <= _REFINE_CHAR_LIMIT and (_azure_available() or _groq_available()):
        logger.info("Running refinement pass on %d chars (source=%s)", len(merged), source)
        merged = await refine_notes(merged)
    elif refine and len(merged) > _REFINE_CHAR_LIMIT:
        logger.info(
            "Skipping refinement pass: notes are %d chars (> %d limit). "
            "Sub-chunk architecture already ensures quality.",
            len(merged), _REFINE_CHAR_LIMIT
        )

    # Verification pass: fact-checks formulas, definitions, and claims.
    # Run always -- correctness is non-negotiable regardless of output size.
    if _azure_available() or _groq_available():
        logger.info("Running verification pass on %d chars", len(merged))
        merged = await verify_notes(merged)

    return merged, source
