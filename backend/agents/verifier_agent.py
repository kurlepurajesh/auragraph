"""
agents/verifier_agent.py

Cross-verification pipeline for the doubt answering flow.

When a student asks a question the system:
  1. Identifies the concept and the relevant note section.
  2. Cross-checks that note section against slide chunks, textbook chunks,
     and the model's own knowledge.
  3. Classifies the note as  correct / partially_correct / incorrect.
  4. Responds with a direct answer plus an explicit correction if needed.
  5. Handles slide OCR noise by not over-relying on slide text.

Structured output separators
─────────────────────────────
The LLM is instructed to use these exact 4 tokens as separators:
    |||VERIFY|||   |||CORRECT|||   |||NOTE|||
Parser : parse_verification_response(text) → VerificationResult
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field


# ── Structured result ─────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    answer:              str = ""          # direct answer to the student
    verification_status: str = "correct"  # correct | partially_correct | incorrect
    correction:          str = ""          # filled only when status != correct
    footnote:            str = ""          # optional short clarification


# ── Verification prompt (replaces the old DOUBT_ANSWER_PROMPT) ────────────────

VERIFICATION_PROMPT = r"""\
You are AuraGraph's Verification Engine — not a simple Q&A chatbot.
Your job is to VERIFY the accuracy of AI-generated study notes and then
answer the student's question with the correct information.

════════════════════════════════════════════════════════════════════════
STUDENT'S QUESTION:
{{$doubt}}

════════════════════════════════════════════════════════════════════════
RELEVANT NOTE PAGE (AI-generated — may contain errors):
{{$note_page}}

════════════════════════════════════════════════════════════════════════
LECTURE SLIDE CONTENT (professor's material — may have OCR noise):
{{$slide_context}}

════════════════════════════════════════════════════════════════════════
TEXTBOOK CONTENT (authoritative reference):
{{$textbook_context}}

════════════════════════════════════════════════════════════════════════
VERIFICATION PROCESS — follow every step:

STEP 1 — UNDERSTAND THE QUESTION
  • Identify the exact concept the student is asking about.
  • Identify which claim in the note page this question relates to.

STEP 2 — CROSS-VERIFY the note's claim against:
  a) Slide content (treat as a rough guide; OCR may be imperfect).
  b) Textbook content (treat as more reliable than slides).
  c) Your own knowledge (treat as ground truth for established theory).
  If slide content contradicts the textbook or your knowledge, trust the
  textbook and your knowledge over the slides.

STEP 3 — CLASSIFY the note's accuracy:
  • correct          — the note's explanation is fully accurate.
  • partially_correct — the note is mostly right but has a gap or
                        imprecise wording that could mislead.
  • incorrect        — the note contains a factual error (wrong formula,
                       wrong sign, wrong operation, wrong definition, etc.)

STEP 4 — DETERMINE YOUR RESPONSE STRATEGY:

  Case: correct
    Answer the question clearly and confirm the notes.

  Case: partially_correct
    Answer the question, noting which part is right and what needs
    clarification.

  Case: incorrect
    ⚠ You MUST start the CORRECTION section with the exact phrase:
        "The notes contain an error."
    Then give the fully corrected explanation with the right formula /
    definition / statement.

STEP 5 — HANDLE SLIDE OCR NOISE
  If slide text looks truncated, garbled, or contradicts basic theory:
  • Do not use it as the primary source.
  • Fall back to textbook context and your own knowledge.
  • Infer the intended concept from context.

STEP 6 — FORMAT YOUR RESPONSE

Use the EXACT separator tokens below (no extra spaces or punctuation):

<Direct answer to the student. Explain the concept clearly. If a formula
 is involved show it in display LaTeX. Add one concrete example if helpful.
 End with one > 📝 **Exam Tip:** if the doubt touches a commonly tested
 misconception.>
|||VERIFY|||
<One word only — exactly one of: correct / partially_correct / incorrect>
|||CORRECT|||
<If status is NOT correct: start with "The notes contain an error." then
 give the full corrected explanation with correct formulas or definitions.
 If status IS correct: write the single word NONE>
|||NOTE|||
<Optional one-sentence clarification visible to the student, or NONE>

FORMATTING RULES:
- Inline math: $...$
- Display math: $$\n...\n$$  (on its own line)
- NEVER use \( \) or \[ \]
- No preamble like "Great question!" or "Sure!"
"""


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_verification_response(text: str) -> VerificationResult:
    """
    Split on |||VERIFY||| / |||CORRECT||| / |||NOTE|||.
    Falls back gracefully if the LLM drifts from the format.
    """
    result = VerificationResult()

    # --- Strategy 1: exact separator tokens ------------------------------------
    parts = re.split(r'\|\|\|VERIFY\|\|\|', text, maxsplit=1)
    if len(parts) == 2:
        result.answer = parts[0].strip()
        remainder     = parts[1]

        correct_split = re.split(r'\|\|\|CORRECT\|\|\|', remainder, maxsplit=1)
        raw_status    = correct_split[0].strip().lower()
        result.verification_status = _normalise_status(raw_status)

        if len(correct_split) == 2:
            note_split     = re.split(r'\|\|\|NOTE\|\|\|', correct_split[1], maxsplit=1)
            raw_correction = note_split[0].strip()
            result.correction = "" if raw_correction.upper() == "NONE" else raw_correction

            if len(note_split) == 2:
                raw_note      = note_split[1].strip()
                result.footnote = "" if raw_note.upper() == "NONE" else raw_note

        return result

    # --- Strategy 2: look for embedded labels ----------------------------------
    status_m = re.search(
        r'(?:Verification\s+(?:Result|Status)|STATUS)[:\s]+'
        r'(correct|partially[_\s]correct|incorrect)',
        text, re.IGNORECASE,
    )
    correction_m = re.search(
        r'(?:Correction|Corrected\s+Explanation)[:\s]+([\s\S]+?)(?=\n(?:Notes?|NOTE|$)|$)',
        text, re.IGNORECASE,
    )
    answer_m = re.search(
        r'(?:Answer)[:\s]+([\s\S]+?)(?=\n(?:Verification|STATUS|$)|$)',
        text, re.IGNORECASE,
    )
    if answer_m:
        result.answer = answer_m.group(1).strip()
    else:
        result.answer = text.strip()   # best-effort: entire text

    if status_m:
        result.verification_status = _normalise_status(status_m.group(1))
    if correction_m:
        raw = correction_m.group(1).strip()
        result.correction = "" if raw.upper() == "NONE" else raw

    return result


def _normalise_status(raw: str) -> str:
    raw = raw.replace(" ", "_").lower().strip(".:; ")
    if "incorrect" in raw:
        return "incorrect"
    if "partial" in raw:
        return "partially_correct"
    return "correct"
