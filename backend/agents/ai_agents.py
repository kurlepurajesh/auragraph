import os
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

FUSION_PROMPT = """\
You are AuraGraph, an expert academic study coach for university and engineering students.

You have been given raw extracted text from two sources:
- **SLIDES TEXT**: Professor's lecture slides (exam scope, key emphasis, formulae)
- **TEXTBOOK TEXT**: Textbook section (conceptual depth, derivations, examples)

SLIDES TEXT:
{slide_summary}

TEXTBOOK TEXT:
{textbook_paragraph}

TARGET PROFICIENCY: {proficiency}
  - Beginner -> USE ALMOST NO MATH. Focus ONLY on Core Concept and Intuition. Use real-world analogies. Plain English.
  - Intermediate -> Balanced depth. Explain the intuition, then show the main formula, then a brief application.
  - Advanced -> Full mathematical rigour. Skip simple analogies. Go straight into definitions, derivations, theorems.

YOUR TASK - Write a COMPLETE, EXAM-ORIENTED STUDY NOTE.

STRICT FORMAT RULES:
1. Use Markdown. Each major topic -> `## Topic`. Sub-topics -> `### Sub-topic`.
2. DO NOT write heading-only sections. Every `##` section MUST have substance.
3. Every `##` section MUST end with a `> **Exam Tip:**` block.
4. For ALL math, use LaTeX: inline `$x = y^2$`, display `$$ \\sum x_i $$`.
5. Total length: 1200-2000 words. Generate 4-8 well-developed sections.
6. Begin directly with the first `##` heading. NO meta-text like "Here is your note".
"""

MUTATION_PROMPT = """\
You are AuraGraph's Adaptive Mutation Agent.
A student is confused about a specific concept in their study note.

ORIGINAL NOTE SECTION:
{original_paragraph}

STUDENT'S DOUBT:
{student_doubt}

TASK:
1. Diagnose the student's conceptual gap in one clear sentence.
2. Rewrite the ORIGINAL NOTE SECTION so it directly resolves the doubt.
   - Add an intuition block explaining WHY it works using an analogy or concrete example.
   - Keep all original formulas in LaTeX. Improve explanations around them.
   - Preserve the Markdown heading if present.
   - Add a `> **Exam Tip:**` if the doubt reveals a commonly tested misconception.
3. Output exactly TWO sections separated by `|||`:

<Fully rewritten section>
|||
<One sentence: the diagnosed conceptual gap>

Do NOT write labels like "Rewritten:" or "Gap:". Just the two sections separated by |||.
"""

EXAMINER_PROMPT = """\
You are AuraGraph's Examiner Agent.
A student is struggling with the following concept:

CONCEPT: {concept_name}

Generate EXACTLY 5 multiple-choice questions (MCQs) that test this concept.

For each question use this format:
Q[n]. [Question text]
A) [Option]
B) [Option]
C) [Option]
D) [Option]
Correct: [Letter]
Explanation: [One clear sentence]

Cover: definition, formula/derivation, application, comparison, and one tricky edge case.
"""


async def ai_fuse(slide_summary: str, textbook_paragraph: str, proficiency: str) -> str:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("No LLM key configured")

    chat = LlmChat(
        api_key=api_key,
        session_id=f"fusion-{os.urandom(4).hex()}",
        system_message="You are AuraGraph, an expert academic study coach that creates exam-oriented study notes."
    ).with_model("openai", "gpt-4o")

    prompt = FUSION_PROMPT.format(
        slide_summary=slide_summary[:6000],
        textbook_paragraph=textbook_paragraph[:6000],
        proficiency=proficiency
    )

    msg = UserMessage(text=prompt)
    response = await chat.send_message(msg)
    return response.strip()


async def ai_mutate(original_paragraph: str, student_doubt: str) -> tuple:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("No LLM key configured")

    chat = LlmChat(
        api_key=api_key,
        session_id=f"mutation-{os.urandom(4).hex()}",
        system_message="You are AuraGraph's Mutation Agent. You rewrite confusing study material to be clearer."
    ).with_model("openai", "gpt-4o")

    prompt = MUTATION_PROMPT.format(
        original_paragraph=original_paragraph[:4000],
        student_doubt=student_doubt[:500]
    )

    msg = UserMessage(text=prompt)
    response = await chat.send_message(msg)
    text = response.strip()

    parts = text.split("|||")
    if len(parts) >= 2:
        rewrite = parts[0].strip()
        gap = " ".join(p.strip() for p in parts[1:]).strip()
        if rewrite and gap:
            return rewrite, gap

    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if len(paragraphs) >= 2:
        last = paragraphs[-1]
        if len(last) < 250 and not last.startswith(('#', '$', '|')):
            return '\n\n'.join(paragraphs[:-1]).strip(), last

    return text, "Student required additional clarification."


async def ai_examine(concept_name: str) -> str:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise ValueError("No LLM key configured")

    chat = LlmChat(
        api_key=api_key,
        session_id=f"examiner-{os.urandom(4).hex()}",
        system_message="You are AuraGraph's Examiner Agent. Generate targeted practice questions."
    ).with_model("openai", "gpt-4o")

    prompt = EXAMINER_PROMPT.format(concept_name=concept_name)
    msg = UserMessage(text=prompt)
    response = await chat.send_message(msg)
    return response.strip()
