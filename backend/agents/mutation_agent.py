"""
agents/mutation_agent.py  — Semantic Kernel 1.x compatible
Adaptive Mutation Loop: rewrites a confusing paragraph based on the student's doubt.
"""

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import PromptTemplateConfig, InputVariable


MUTATION_PROMPT = """\
You are AuraGraph's Adaptive Mutation Agent.
A student is confused about a specific concept in their study note.

---
ORIGINAL NOTE SECTION:
{{$original_paragraph}}

STUDENT'S DOUBT:
{{$student_doubt}}

---
TASK:
1. Diagnose the student's conceptual gap in one clear sentence.
2. Rewrite the ORIGINAL NOTE SECTION so it directly resolves the doubt.
   - Add an intuition block (💡) explaining WHY it works using an analogy or concrete example.
   - Keep all original formulas. Use ONLY `$...$` for inline math and `$$` on its own line for display math. NEVER use \\( \\) or \\[ \\] delimiters.
   - Preserve the Markdown heading if present.
   - Add a `> 📝 **Exam Tip:**` if the doubt reveals a commonly tested misconception.
3. Output exactly TWO sections separated by `|||` (three pipe characters, no spaces around):

<Fully rewritten section that replaces the original>
|||
<One sentence: the diagnosed conceptual gap>

Do NOT write labels like "Rewritten:" or "Gap:". Just the two sections separated by |||.
"""


class MutationAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel
        config = PromptTemplateConfig(
            template=MUTATION_PROMPT,
            template_format="semantic-kernel",
            input_variables=[
                InputVariable(name="original_paragraph", description="The note section to rewrite"),
                InputVariable(name="student_doubt", description="What the student is confused about"),
            ],
        )
        self._fn = kernel.add_function(
            function_name="mutate",
            plugin_name="MutationAgent",
            prompt_template_config=config,
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
        text = str(result).strip()

        # ── Try to split on ||| with increasing leniency ─────────────────────
        # Strategy 1: exact |||  separator (as instructed)
        parts = text.split("|||")
        if len(parts) >= 2:
            rewrite = parts[0].strip()
            gap    = " ".join(p.strip() for p in parts[1:]).strip()
            if rewrite and gap:
                return rewrite, gap

        # Strategy 2: LLM used newline-separated "Gap:" / labelled sections
        import re as _re
        gap_match = _re.search(
            r'(?:^|\n)(?:Gap|Conceptual\s+Gap|Diagnosed\s+Gap|Issue)[:\s]+(.+)',
            text, _re.IGNORECASE
        )
        rewrite_match = _re.search(
            r'(?:^|\n)(?:Rewritten?(?:\s+Section)?)[:\s]+([\s\S]+?)(?=\n(?:Gap|\||$)|$)',
            text, _re.IGNORECASE
        )
        if gap_match and rewrite_match:
            return rewrite_match.group(1).strip(), gap_match.group(1).strip()

        # Strategy 3: last paragraph is likely the gap sentence
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if len(paragraphs) >= 2:
            last = paragraphs[-1]
            # A gap sentence is short and doesn't start with # or $
            if len(last) < 250 and not last.startswith(('#', '$', '|')):
                return '\n\n'.join(paragraphs[:-1]).strip(), last

        # Strategy 4: return entire text as rewrite with generic gap
        return text, "Student required additional clarification."
