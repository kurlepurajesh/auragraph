"""
agents/fusion_agent.py
Knowledge Fusion Engine — merges professor slides with textbook paragraphs
into a single proficiency-calibrated study note.
"""

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import PromptTemplateConfig


FUSION_PROMPT = """
You are AuraGraph, an expert academic study coach for university and engineering students in India.

You have been given raw extracted text from two sources for a course topic:
- **SLIDES TEXT**: Professor's lecture slides (defines exam scope, key emphasis, formulae)
- **TEXTBOOK TEXT**: Corresponding textbook section (provides conceptual depth, derivations, examples)

SLIDES TEXT:
{{$slide_summary}}

TEXTBOOK TEXT:
{{$textbook_paragraph}}

TARGET PROFICIENCY: {{$proficiency}}
  - Beginner    → plain English, every term defined, real-world analogies before formulas
  - Intermediate → clear prose, key terms defined inline, formula then intuition
  - Advanced    → rigorous, full mathematical depth, derivations where useful

---
YOUR TASK — Generate a COMPLETE STRUCTURED STUDY NOTE with these rules:

1. **Format**: Use Markdown. Each major topic → `## Topic`. Sub-topics → `### Sub-topic`. Key terms in **bold**. Equations in `backticks` or LaTeX style.

2. **Every `##` section must contain ALL of**:
   a. A crisp 1-2 sentence definition/overview
   b. Explanation with intuition (why it works, not just what it is)
   c. Key formula or principle (if applicable), clearly labelled
   d. A short example — verbal or numeric — that makes it concrete
   e. A 📝 **Exam Tip** line: what examiners typically ask about this, common mistakes, marks-worthy points

3. **Tone**: A brilliant professor explaining to a motivated student — precise, clear, engaging. NOT a dictionary. NOT bullet-only.

4. **Calibration to proficiency**: {{$proficiency}} level — adjust density, jargon, and depth of derivation accordingly.

5. **Length**: 1000–1800 words total. Depth over breadth. Do NOT generate empty or heading-only sections.

6. **Exam orientation**: Structure the note around what appears in university examinations — definitions, derivations, applications, comparison questions.

7. Begin directly with the first `##` heading. Do NOT write meta-text like "Here is your note" or "Sure!".
"""


class FusionAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        self._fn = kernel.add_function(
            function_name="fuse",
            plugin_name="FusionAgent",
            prompt=FUSION_PROMPT,
            prompt_template_settings=PromptTemplateConfig(
                template_format="semantic-kernel"
            ),
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
