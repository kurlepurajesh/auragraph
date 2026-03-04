"""
agents/mutation_agent.py
Adaptive Mutation Loop — Rewrites confusing paragraphs directly inline based on user doubt.
"""

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import PromptTemplateConfig

MUTATION_PROMPT = """
You are AuraGraph's Adaptive Mutation Agent.
A student is struggling with a specific concept in their study note.

---
ORIGINAL PARAGRAPH:
{{$original_paragraph}}

STUDENT DOUBT/CONFUSION:
{{$student_doubt}}

---
TASK:
1. Identify the conceptual gap the student has.
2. Rewrite the ORIGINAL PARAGRAPH so that it directly resolves the student's doubt. Use analogies, simpler language, or step-by-step logic based on what confused them.
3. Your output must contain TWO sections, separated exactly by the sequence '|||'

Format Output:
<Rewritten paragraph that replaces the original>
|||
<A single short sentence explaining the diagnosed conceptual gap>

Do not include labels like 'Rewritten:' or 'Gap:'. Just the output separated by '|||'.
"""


class MutationAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        self._fn = kernel.add_function(
            function_name="mutate",
            plugin_name="MutationAgent",
            prompt=MUTATION_PROMPT,
            prompt_template_settings=PromptTemplateConfig(
                template_format="semantic-kernel"
            ),
        )

    async def mutate(
        self,
        original_paragraph: str,
        student_doubt: str,
    ) -> tuple[str, str]:
        args = KernelArguments(
            original_paragraph=original_paragraph,
            student_doubt=student_doubt,
        )
        result = await self._kernel.invoke(self._fn, args)
        
        # Split output based on the separator 
        parts = str(result).split("|||")
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
        return str(result).strip(), "Student showed conceptual misunderstanding."
