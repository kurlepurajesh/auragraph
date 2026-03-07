"""
agents/examiner_agent.py  — Semantic Kernel 1.x compatible
Examiner Agent: generates targeted MCQ practice questions for a concept.
"""

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import PromptTemplateConfig, InputVariable


EXAMINER_PROMPT = """\
You are AuraGraph's Examiner Agent.
A student is struggling with the following concept:

CONCEPT: {{$concept_name}}

COURSE CONTEXT — retrieved from the student's own slides, notes, and textbooks:
{{$notebook_context}}

TASK:
Generate EXACTLY 5 multiple-choice questions (MCQs) that test this concept.
Base ALL questions on the course context above — do NOT use general knowledge from
other fields. For example, if the context is about probability, "Bernoulli" means
Bernoulli Distribution, NOT Bernoulli's principle in fluid mechanics.
Focus on the most commonly examined aspects and typical exam mistakes.

For each question use this format:
Q[n]. [Question text]
A) [Option]
B) [Option]
C) [Option]
D) [Option]
✅ Correct: [Letter]
💡 Explanation: [One clear sentence explaining why]

Cover: definition, formula/derivation, application, comparison, and one tricky edge case.
Use ONLY `$...$` for inline math and `$$` on its own line for display math. NEVER use \\( \\) or \\[ \\] delimiters.
{{$custom_instruction}}"""


CONCEPT_PRACTICE_PROMPT = """\
You are AuraGraph's Concept Practice Engine. Generate exactly 3 targeted MCQ questions.

CONCEPT: {{$concept_name}}
DIFFICULTY: {{$level}}

COURSE CONTEXT — from the student's own slides, notes, and textbooks:
{{$notebook_context}}

DIFFICULTY GUIDE:
  struggling  → Foundational — definitions, basic recall, single-step application.
  partial     → Standard — formula application, typical exam-style problems.
  mastered    → Advanced / Exam Level — edge cases, derivations, tricky variants, subtle distinctions.

IMPORTANT: Ground all questions in the COURSE CONTEXT above. Use terminology, formulas,
and examples exactly as they appear in the student's materials. Never introduce content
from unrelated fields even if the concept name is ambiguous.

Output ONLY a valid JSON array of exactly 3 objects.
No markdown code fences, no prose, no backticks — raw JSON only.

Each object must have EXACTLY these keys:
  "question"    : the full question text (string)
  "options"     : object with exactly keys A, B, C, D (all strings)
  "correct"     : the letter of the correct option ("A", "B", "C", or "D")
  "explanation" : one clear sentence explaining why the answer is correct

Math rules: inline $...$, display on its own line $$...$$. NEVER use \\( \\) or \\[ \\].
{{$custom_instruction}}"""


SNIPER_EXAM_PROMPT = """\
You are AuraGraph's Sniper Examiner. Generate EXACTLY 5 targeted MCQ questions.

TARGET CONCEPTS — Struggling (70% weight → questions 1, 2, 3):
{{$struggling_concepts}}

REVIEW CONCEPTS — Partial (30% weight → questions 4, 5):
{{$partial_concepts}}

COURSE CONTEXT — from the student's own slides, notes, and textbooks (ground ALL questions here):
{{$notebook_context}}

ALLOCATION RULES:
  • Questions 1–3 MUST test the struggling concepts — rotate evenly if multiple.
  • Questions 4–5 MUST test the partial concepts — rotate evenly if multiple.
  • If only struggling concepts exist, spread them across all 5 questions.
  • If only partial concepts exist, spread them across all 5 questions.
  • Base EVERY question on the course context above — no outside-field content.

Output ONLY a valid JSON array of exactly 5 objects. Raw JSON, no markdown fences.
Each object MUST have EXACTLY these keys:
  "question"    : full question text (string)
  "options"     : object with keys A, B, C, D (all strings)
  "correct"     : the correct option letter ("A", "B", "C", or "D")
  "explanation" : one clear sentence explaining the answer
  "concept"     : the concept this question tests

Math: inline $...$, display $$...$$ on its own line. NEVER use \\( \\) or \\[ \\].
"""

class ExaminerAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        config = PromptTemplateConfig(
            template=EXAMINER_PROMPT,
            template_format="semantic-kernel",
            input_variables=[
                InputVariable(name="concept_name", description="The concept to generate questions for"),
                InputVariable(name="notebook_context", description="Retrieved course material context", default_value="(no course context available)", is_required=False),
                InputVariable(name="custom_instruction", description="Optional extra instruction from the student", default_value="", is_required=False),
            ],
        )
        self._fn = kernel.add_function(
            function_name="examine",
            plugin_name="ExaminerAgent",
            prompt_template_config=config,
        )
        practice_config = PromptTemplateConfig(
            template=CONCEPT_PRACTICE_PROMPT,
            template_format="semantic-kernel",
            input_variables=[
                InputVariable(name="concept_name", description="Concept to generate questions for"),
                InputVariable(name="level", description="Difficulty level: struggling / partial / mastered"),
                InputVariable(name="notebook_context", description="Retrieved course material context", default_value="(no course context available)", is_required=False),
                InputVariable(name="custom_instruction", description="Optional extra instruction from the student", default_value="", is_required=False),
            ],
        )
        self._practice_fn = kernel.add_function(
            function_name="concept_practice",
            plugin_name="ExaminerAgent",
            prompt_template_config=practice_config,
        )

    async def examine(self, concept_name: str, notebook_context: str = "", custom_instruction: str = "") -> str:
        ci = f"\n\nCUSTOM FOCUS (follow exactly): {custom_instruction}" if custom_instruction.strip() else ""
        ctx = notebook_context or "(no course context available)"
        args = KernelArguments(concept_name=concept_name, notebook_context=ctx, custom_instruction=ci)
        result = await self._kernel.invoke(self._fn, args)
        return str(result).strip()

    async def concept_practice(self, concept_name: str, level: str, notebook_context: str = "", custom_instruction: str = "") -> str:
        ci = f"\n\nCUSTOM FOCUS (follow exactly): {custom_instruction}" if custom_instruction.strip() else ""
        ctx = notebook_context or "(no course context available)"
        args = KernelArguments(concept_name=concept_name, level=level, notebook_context=ctx, custom_instruction=ci)
        result = await self._kernel.invoke(self._practice_fn, args)
        return str(result).strip()
