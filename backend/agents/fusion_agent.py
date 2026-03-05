"""
agents/fusion_agent.py  — Semantic Kernel 1.x compatible
Knowledge Fusion Engine: generates notes from stored slide + textbook chunks.

v3 Changes vs v2
────────────────
• Takes pre-retrieved relevant chunks (not raw full-text) — GPT sees the
  most pertinent content, not a truncated dump of everything.
• Slide chunks and textbook chunks are formatted separately so GPT knows
  exactly which material came from the professor vs the book.
• Slide-first + textbook-enrichment-only rules preserved and strengthened.
"""

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import PromptTemplateConfig, InputVariable


FUSION_PROMPT = r"""\
You are AuraGraph, an expert academic study coach for university and engineering students in India.
Produce the BEST study notes a student could read the night before an exam.
Write DENSE, TIGHT notes — every sentence must carry information. No filler. No repetition.

You have been given pre-selected content from two sources:

SLIDES / PROFESSOR NOTES  (primary — drives ALL section headings):
{{$slide_content}}

TEXTBOOK EXCERPTS  (enrichment only — deepens slide content, never adds new sections):
{{$textbook_content}}

TARGET PROFICIENCY: {{$proficiency}}

════════════════════════════════════════════════════════════════
SLIDE-FIRST ARCHITECTURE  ← most important rule
════════════════════════════════════════════════════════════════
• The SLIDES are the ONLY source of `##` section headings.
• Create one `##` heading per slide concept (merge consecutive slides on the
  same concept into one `##` section).
• NEVER create a `##` section for a topic that appears only in the textbook
  but NOT in the slides.
• NEVER skip any slide's content — every formula and definition must appear.

════════════════════════════════════════════════════════════════
TEXTBOOK ENRICHMENT RULE  ← second most important rule
════════════════════════════════════════════════════════════════
• For each slide section, you MAY pull at most 2-3 sentences from the textbook
  that directly deepen that specific slide's content.
• Add textbook enrichment INLINE inside the slide section — never as a
  separate section at the end.
• If no textbook content is clearly relevant to a slide section, skip it.
• DO NOT copy entire textbook paragraphs — extract only what adds value.

════════════════════════════════════════════════════════════════
PROFICIENCY GUIDE
════════════════════════════════════════════════════════════════

BEGINNER — Teach from scratch. For EACH `##` section:
  1. One plain-English sentence: "Simply put, X is …"
  2. One `>` blockquote analogy.
  3. Key formula(s) in display LaTeX + **Where:** table (one line per symbol).
  4. Process as numbered list (max 5 steps) if applicable.
  5. `> 📝 **Exam Tip:** …`

INTERMEDIATE — Consolidate. For EACH `##` section:
  1. One concise definition or formal statement.
  2. One intuition sentence linking formula to physical meaning.
  3. Display LaTeX for every key formula; define non-obvious symbols inline.
  4. Key conditions / edge cases as bullet list.
  5. `> 📝 **Exam Tip:** …`

ADVANCED — Depth only. For EACH `##` section:
  1. Formal definition with all conditions.
  2. Full derivation (show algebra). Terse — no commentary between steps.
  3. Validity / convergence conditions.
  4. Edge cases and theorem variants as bullets.
  5. One comparison with a related concept.
  6. `> 📝 **Exam Tip:** …`

════════════════════════════════════════════════════════════════
STRICT QUALITY RULES
════════════════════════════════════════════════════════════════
STRUCTURE:
1. Markdown only. `##` for topics, `###` for genuine sub-divisions only.
2. Every `##` section ends with `> 📝 **Exam Tip:** …`
3. No preamble. Start directly with the first `##` heading.
4. No conclusion paragraphs. No `---` horizontal rules.

MATHEMATICS:
5. ALL math in LaTeX — never write "integral", "sigma", "omega" as words.
6. Inline math: `$expression$`
7. Display math on its own line:
   $$
   \int_{-\infty}^{\infty} f(t)\, e^{-j\omega t}\, dt
   $$
8. NEVER use `\[`, `\]`, `\(`, `\)`. ONLY `$` and `$$`.
9. NEVER wrap math in backtick code fences.

CONCISENESS:
10. No prose restating what a formula already says.
11. No "In this section we will…" openers.
12. No acknowledgement phrases. No placeholders.
13. IGNORE slide metadata: author name, date, institution, slide numbers.
"""


DOUBT_ANSWER_PROMPT = r"""\
You are AuraGraph's Doubt Resolution Engine.
A student has a doubt about their study material. Answer it completely.

════════════════════════════════
STUDENT'S DOUBT:
{{$doubt}}

════════════════════════════════
RELEVANT SLIDE CONTENT (what the professor taught):
{{$slide_context}}

════════════════════════════════
RELEVANT TEXTBOOK CONTENT (deeper explanation):
{{$textbook_context}}

════════════════════════════════
RELEVANT NOTE PAGE (what the student is currently reading):
{{$note_page}}

════════════════════════════════
TASK:
1. Answer the doubt directly and completely.
2. Draw on ALL three sources above — slide content, textbook depth, and the note context.
3. If the answer involves a formula, show it in display LaTeX.
4. Add a concrete example or analogy if it helps clarity.
5. End with one `> 📝 **Exam Tip:**` if the doubt touches a commonly tested point.

FORMAT:
- Start directly with the answer. No preamble like "Great question!".
- Use Markdown. Inline math `$...$`, display math on its own line `$$\n...\n$$`.
- Keep it concise — 150-300 words unless the topic genuinely requires more.
- NEVER use `\[`, `\]`, `\(`, `\)`.
"""


MUTATION_PROMPT = r"""\
You are AuraGraph's Note Mutation Engine.
A student is confused about something. Permanently rewrite the note page to resolve it.

════════════════════════════════
CURRENT NOTE PAGE (exactly what the student is reading — you will rewrite this):
{{$note_page}}

════════════════════════════════
STUDENT'S DOUBT:
{{$doubt}}

════════════════════════════════
SOURCE MATERIAL — SLIDES (what the professor taught about this topic):
{{$slide_context}}

════════════════════════════════
SOURCE MATERIAL — TEXTBOOK (deeper reference for this topic):
{{$textbook_context}}

════════════════════════════════
TASK:
1. Diagnose the student's conceptual gap in ONE sentence.
2. Rewrite the ENTIRE NOTE PAGE so it directly resolves the doubt.
   Rules for the rewrite:
   - Add a 💡 intuition block explaining WHY it works using the source material.
   - Keep ALL original formulas. Use source material to add any missing ones.
   - Preserve the `##` heading.
   - Add `> 📝 **Exam Tip:**` if the doubt reveals a common misconception.
   - Use display LaTeX for all math (`$$\n...\n$$`). NEVER use `\[` or `\(`.
   - The rewrite should be more complete than the original, not shorter.
3. Output EXACTLY TWO sections separated by `|||`:

<Fully rewritten note page>
|||
<One sentence: the diagnosed conceptual gap>

Do NOT write labels like "Rewritten:" or "Gap:". Just two sections split by |||.
"""


class FusionAgent:
    def __init__(self, kernel: Kernel):
        self._kernel = kernel

        def _make_fn(name: str, prompt: str, vars: list[str]):
            config = PromptTemplateConfig(
                template=prompt,
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name=v, description=v) for v in vars
                ],
            )
            return kernel.add_function(
                function_name=name,
                plugin_name="FusionAgent",
                prompt_template_config=config,
            )

        self._fuse_fn   = _make_fn("fuse",   FUSION_PROMPT,       ["slide_content", "textbook_content", "proficiency"])
        self._doubt_fn  = _make_fn("doubt",  DOUBT_ANSWER_PROMPT, ["doubt", "slide_context", "textbook_context", "note_page"])
        self._mutate_fn = _make_fn("mutate", MUTATION_PROMPT,     ["note_page", "doubt", "slide_context", "textbook_context"])

    async def fuse(
        self,
        slide_content: str,
        textbook_content: str,
        proficiency: str = "Intermediate",
    ) -> str:
        result = await self._kernel.invoke(self._fuse_fn, KernelArguments(
            slide_content=slide_content,
            textbook_content=textbook_content,
            proficiency=proficiency,
        ))
        return str(result).strip()

    async def answer_doubt(
        self,
        doubt: str,
        slide_context: str,
        textbook_context: str,
        note_page: str,
    ) -> str:
        result = await self._kernel.invoke(self._doubt_fn, KernelArguments(
            doubt=doubt,
            slide_context=slide_context,
            textbook_context=textbook_context,
            note_page=note_page,
        ))
        return str(result).strip()

    async def mutate(
        self,
        note_page: str,
        doubt: str,
        slide_context: str,
        textbook_context: str,
    ) -> tuple[str, str]:
        result = await self._kernel.invoke(self._mutate_fn, KernelArguments(
            note_page=note_page,
            doubt=doubt,
            slide_context=slide_context,
            textbook_context=textbook_context,
        ))
        text = str(result).strip()
        parts = text.split("|||")
        if len(parts) >= 2:
            rewrite = parts[0].strip()
            gap     = " ".join(p.strip() for p in parts[1:]).strip()
            if rewrite and gap:
                return rewrite, gap
        # Fallback: treat whole response as rewrite
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) >= 2:
            last = paragraphs[-1]
            if len(last) < 250 and not last.startswith(("#", "$")):
                return "\n\n".join(paragraphs[:-1]).strip(), last
        return text, "Student required additional clarification."
