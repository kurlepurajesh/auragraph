import os
import re
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)


def fix_latex_delimiters(text: str) -> str:
    """Convert all LaTeX delimiter formats to $ and $$ that rehype-katex understands."""
    # Fix display math: \[ ... \] -> $$ ... $$
    text = re.sub(r'\\\[\s*', '\n$$\n', text)
    text = re.sub(r'\s*\\\]', '\n$$\n', text)
    # Fix inline math: \( ... \) -> $ ... $
    text = re.sub(r'\\\(\s*', ' $', text)
    text = re.sub(r'\s*\\\)', '$ ', text)
    # Fix bare bracket math: [ formula ] at start of line (common AI output)
    text = re.sub(r'^\[\s*(.+?)\s*\]\s*$', r'$$ \1 $$', text, flags=re.MULTILINE)
    # Clean up multiple $$ on same line
    text = re.sub(r'\$\$\s*\$\$', '$$', text)
    # Fix double-newlines inside display math
    lines = text.split('\n')
    result = []
    in_display = False
    for line in lines:
        stripped = line.strip()
        if stripped == '$$':
            in_display = not in_display
            result.append(line)
        elif in_display and stripped == '':
            continue  # skip blank lines inside $$ blocks
        else:
            result.append(line)
    return '\n'.join(result)


FUSION_PROMPT = """\
You are AuraGraph, an expert academic study coach. You create comprehensive, exam-oriented study notes for university students.

SOURCE MATERIAL:

--- PROFESSOR'S SLIDES (defines exam scope) ---
{slide_summary}

--- TEXTBOOK (provides depth) ---
{textbook_paragraph}

TARGET PROFICIENCY: {proficiency}

PROFICIENCY GUIDELINES:
- **Beginner**: Explain EVERY concept in detail with real-world analogies, step-by-step breakdowns, and worked examples. Include formulas but always explain what each symbol means and walk through a concrete numerical example. Use simple language. Make it feel like a patient tutor explaining to someone seeing this for the first time.
- **Intermediate**: Balanced depth. State the concept, give a brief intuition, show the formula with variable definitions, and include one application example. Cover all topics thoroughly.
- **Advanced**: Rigorous and concise. State definitions precisely, show complete derivations/proofs, include edge cases and comparisons between related concepts. Add advanced exam-oriented tricks and common pitfalls.

CRITICAL RULES:
1. **COVER EVERY SINGLE TOPIC** mentioned in the slides. Do NOT skip any concept, formula, or topic the professor included. If the slides mention 10 topics, your note MUST have sections for all 10.
2. Use Markdown: `## Topic` for each major concept, `### Sub-topic` for subtopics.
3. Every `##` section MUST have substantial content (not just a heading).
4. Every `##` section MUST end with `> **Exam Tip:** ...`
5. For ALL math formulas, use ONLY these LaTeX delimiters:
   - Inline math: `$formula$` (e.g., $E(X) = np$)
   - Display math on its own line: `$$` then formula then `$$` (each $$ on its own line)
   - NEVER use \\[ \\] or \\( \\) delimiters. ONLY use $ and $$.
6. For Beginner: After every formula, add "**In words:** ..." explaining it in plain English.
7. Generate comprehensive notes. DO NOT artificially limit length. Cover everything properly.
8. Begin directly with `## ` heading. No preamble like "Here are your notes".
"""

MUTATION_PROMPT = """\
You are AuraGraph's Adaptive Mutation Agent. A student is reading their study notes and got confused on a section. Your job is to REWRITE that section so the confusion is permanently resolved.

ORIGINAL NOTE SECTION THE STUDENT IS READING:
---
{original_paragraph}
---

THE STUDENT'S DOUBT / CONFUSION:
"{student_doubt}"

YOUR TASK:
Rewrite the ENTIRE original section above so it directly addresses and resolves the student's confusion. Your rewrite must:

1. Keep the same `## ` or `### ` heading if one exists in the original
2. Add a clear intuition/analogy block near the top that directly addresses the doubt
3. Re-explain the concept in simpler, more accessible language
4. Keep all formulas but explain every symbol. Use ONLY $...$ for inline math and $$ on its own line for display math. NEVER use \\( \\) or \\[ \\] delimiters.
5. Add a worked numerical example if the doubt involves a formula
6. End with `> **Exam Tip:** ...` highlighting a common misconception related to the doubt

OUTPUT FORMAT - Output exactly two parts separated by the delimiter `|||`:

PART 1: The fully rewritten section (complete markdown, ready to replace the original)
|||
PART 2: One sentence describing the conceptual gap you identified

Example output structure:
## Topic Name

> **Intuition:** [analogy or simple explanation addressing the doubt]

[Rewritten content...]

> **Exam Tip:** [tip]
|||
The student did not understand [specific gap].
"""

EXAMINER_PROMPT = """\
You are AuraGraph's Examiner Agent.
A student is struggling with the following concept:

CONCEPT: {concept_name}

Generate EXACTLY 5 multiple-choice questions (MCQs) that test this concept.
Use ONLY $...$ for inline math and $$ on its own line for display math. NEVER use \\( \\) or \\[ \\].

For each question use this format:

**Q[n].** [Question text]

A) [Option]
B) [Option]
C) [Option]
D) [Option]

**Correct:** [Letter]

**Explanation:** [One clear sentence]

---

Cover: definition, formula/derivation, application, comparison, and one tricky edge case.
"""


async def ai_fuse(slide_summary: str, textbook_paragraph: str, proficiency: str) -> str:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("No LLM key configured")

    chat = LlmChat(
        api_key=api_key,
        session_id=f"fusion-{os.urandom(4).hex()}",
        system_message="You are AuraGraph, an expert academic study coach. You create thorough, exam-oriented study notes. Use $ for inline math and $$ for display math. Never use \\( \\) or \\[ \\] delimiters."
    ).with_model("openai", "gpt-4o")

    prompt = FUSION_PROMPT.format(
        slide_summary=slide_summary[:8000],
        textbook_paragraph=textbook_paragraph[:8000],
        proficiency=proficiency
    )

    msg = UserMessage(text=prompt)
    response = await chat.send_message(msg)
    result = response.strip()
    result = fix_latex_delimiters(result)
    return result


async def ai_mutate(original_paragraph: str, student_doubt: str) -> tuple:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("No LLM key configured")

    chat = LlmChat(
        api_key=api_key,
        session_id=f"mutation-{os.urandom(4).hex()}",
        system_message="You are AuraGraph's Mutation Agent. You rewrite confusing study material to be clearer and more intuitive. Use $ for inline math and $$ for display math. Never use \\( \\) or \\[ \\] delimiters. Always output the rewritten section followed by ||| followed by a one-sentence gap diagnosis."
    ).with_model("openai", "gpt-4o")

    prompt = MUTATION_PROMPT.format(
        original_paragraph=original_paragraph[:5000],
        student_doubt=student_doubt[:500]
    )

    msg = UserMessage(text=prompt)
    response = await chat.send_message(msg)
    text = response.strip()
    text = fix_latex_delimiters(text)

    # Parse the ||| separator
    if '|||' in text:
        parts = text.split('|||', 1)
        rewrite = parts[0].strip()
        gap = parts[1].strip() if len(parts) > 1 else "Student required additional clarification."
        if rewrite:
            return rewrite, gap

    # Fallback: try to separate last short paragraph as gap diagnosis
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if len(paragraphs) >= 2:
        last = paragraphs[-1]
        if len(last) < 300 and not last.startswith(('#', '$', '>', '|', '-', '*')):
            return '\n\n'.join(paragraphs[:-1]).strip(), last

    return text, "Student required additional clarification on this concept."


async def ai_examine(concept_name: str) -> str:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("No LLM key configured")

    chat = LlmChat(
        api_key=api_key,
        session_id=f"examiner-{os.urandom(4).hex()}",
        system_message="You are AuraGraph's Examiner Agent. Generate targeted practice questions. Use $ for inline math and $$ for display math. Never use \\( \\) or \\[ \\] delimiters."
    ).with_model("openai", "gpt-4o")

    prompt = EXAMINER_PROMPT.format(concept_name=concept_name)
    msg = UserMessage(text=prompt)
    response = await chat.send_message(msg)
    result = response.strip()
    result = fix_latex_delimiters(result)
    return result
