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

TASK:
Generate EXACTLY 5 multiple-choice questions (MCQs) that test this concept,
focusing on the most commonly examined aspects and typical exam mistakes.

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
"""


class ExaminerAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        config = PromptTemplateConfig(
            template=EXAMINER_PROMPT,
            template_format="semantic-kernel",
            input_variables=[
                InputVariable(name="concept_name", description="The concept to generate questions for"),
            ],
        )
        self._fn = kernel.add_function(
            function_name="examine",
            plugin_name="ExaminerAgent",
            prompt_template_config=config,
        )

    async def examine(self, concept_name: str) -> str:
        args = KernelArguments(concept_name=concept_name)
        result = await self._kernel.invoke(self._fn, args)
        return str(result).strip()
