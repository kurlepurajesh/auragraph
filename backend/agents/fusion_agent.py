"""
agents/fusion_agent.py  — Semantic Kernel 1.x compatible
Knowledge Fusion Engine: merges professor slides with textbook text
into a proficiency-calibrated, exam-oriented study note.
"""

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import PromptTemplateConfig, InputVariable


FUSION_PROMPT = """\
You are AuraGraph, an expert academic study coach for university and engineering students in India.

You have been given raw extracted text from two sources:
- **SLIDES TEXT**: Professor's lecture slides (exam scope, key emphasis, formulae)
- **TEXTBOOK TEXT**: Textbook section (conceptual depth, derivations, examples)

SLIDES TEXT:
{{$slide_summary}}

TEXTBOOK TEXT:
{{$textbook_paragraph}}

TARGET PROFICIENCY: {{$proficiency}}
  - Beginner    → plain English, every term defined, real-world analogies first, formulas last
  - Intermediate → balanced: prose explanation + formula + brief derivation
  - Advanced    → full mathematical rigour, complete derivations, edge-case conditions

---
YOUR TASK — Write a COMPLETE, EXAM-ORIENTED STUDY NOTE.

STRICT FORMAT RULES:
1. Use Markdown. Each major topic → `## Topic`. Sub-topics → `### Sub-topic`.
2. DO NOT write heading-only sections. Every `##` section MUST have ALL of:
   a. 1-2 sentence crisp definition/overview
   b. Intuition — WHY it works (not just what it is)
   c. Key formula clearly wrapped in LaTeX: `$$formula$$`
   d. A short worked example (verbal or numeric)
   e. `> 📝 **Exam Tip:**` line with what examiners ask, common mistakes, mark-worthy phrases

3. Write like a brilliant professor — precise, engaging, NOT a dictionary, NOT bullets-only.
4. Adjust density/jargon for {{$proficiency}} level.
5. Total length: 1200–2000 words. Depth over breadth. Generate 4-8 well-developed sections.
6. Structure around what appears in university examinations: definitions, derivations, applications.
7. For all mathematical expressions use proper LaTeX wrapped in `$$...$$` for display math.
8. Begin directly with the first `##` heading. NO meta-text like "Here is your note" or "Sure!".
"""


class FusionAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        config = PromptTemplateConfig(
            template=FUSION_PROMPT,
            template_format="semantic-kernel",
            input_variables=[
                InputVariable(name="slide_summary", description="Slides text"),
                InputVariable(name="textbook_paragraph", description="Textbook text"),
                InputVariable(name="proficiency", description="Student proficiency level"),
            ],
        )
        self._fn = kernel.add_function(
            function_name="fuse",
            plugin_name="FusionAgent",
            prompt_template_config=config,
        )

    async def fuse(
        self,
        slide_summary: str,
        textbook_paragraph: str,
        proficiency: str = "Intermediate",
    ) -> str:
        args = KernelArguments(
            slide_summary=slide_summary,
            textbook_paragraph=textbook_paragraph,
            proficiency=proficiency,
        )
        result = await self._kernel.invoke(self._fn, args)
        return str(result).strip()
