"""
agents/examiner_agent.py
Examiner Agent — Generates multiple-choice targeted practice questions based on weak zones.
"""

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import PromptTemplateConfig

EXAMINER_PROMPT = """
You are AuraGraph's Examiner Agent.
A student is struggling with the following conceptual node:
CONCEPT: {{$concept_name}}

TASK:
Generate EXACTLY 3 multiple-choice questions (MCQs) to test their understanding of this specific concept and its typical pitfalls.
For each question:
- Provide 4 options (A, B, C, D).
- Indicate the correct answer.
- Provide a very brief explanation (1 sentence) of why it's correct.

Format Output exactly like this for each question:
Q1. [Question text]?
A) [Option]
B) [Option]
C) [Option]
D) [Option]
Correct: [Letter]
Explanation: [Text]
"""

class ExaminerAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        self._fn = kernel.add_function(
            function_name="examine",
            plugin_name="ExaminerAgent",
            prompt=EXAMINER_PROMPT,
            prompt_template_settings=PromptTemplateConfig(
                template_format="semantic-kernel"
            ),
        )

    async def examine(
        self,
        concept_name: str,
    ) -> str:
        args = KernelArguments(
            concept_name=concept_name,
        )
        result = await self._kernel.invoke(self._fn, args)
        return str(result).strip()
