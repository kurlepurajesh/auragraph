"""
agents/latex_utils.py
Utility: normalize all LaTeX delimiter variants to $ / $$ (rehype-katex friendly).

Any AI-generated text may use \\[ \\] or \\( \\) — this converter normalises them
so that remark-math + rehype-katex renders them correctly.

remark-math rules:
  • Inline math  : $expression$   (no spaces between $ and content)
  • Display math : a paragraph that contains ONLY $$\n…\n$$ — the opening $$
    must be preceded by a blank line (or start-of-document) and the closing $$
    must be followed by a blank line (or end-of-document).
"""

import re


def fix_latex_delimiters(text: str) -> str:
    """
    Normalise all LaTeX delimiter variants to $ / $$ for rehype-katex.

    Steps applied in order
    ──────────────────────
    1. \\( … \\)  (inline)  →  $…$          (DOTALL: handles multi-line)
    2. \\[ … \\]  (display) →  block $$…$$  (DOTALL: handles multi-line)
    3. Inline $$content$$ (no newlines in content) → block form
    4. Ensure every standalone $$ line has a blank line before it (opener)
       and a blank line after it (closer)  so remark-math parses them as
       block-level math nodes.
    5. Collapse 3+ consecutive blank lines → 2
    """

    # ── 1. \\(...\\) → $...$  ────────────────────────────────────────────────
    # DOTALL so \(\n formula \n\) still matches; strip internal whitespace.
    text = re.sub(
        r'\\\(\s*(.*?)\s*\\\)',
        lambda m: '$' + m.group(1).strip() + '$',
        text,
        flags=re.DOTALL,
    )

    # ── 2. \\[...\\] → block $$...$$ ─────────────────────────────────────────
    text = re.sub(
        r'\\\[\s*(.*?)\s*\\\]',
        lambda m: '\n\n$$\n' + m.group(1).strip() + '\n$$\n\n',
        text,
        flags=re.DOTALL,
    )

    # ── 3. Inline $$content$$ (single line, no embedded newlines) → block ────
    # Matches $$X$$ where X contains no newlines and no lone $.
    # Lookbehind/lookahead prevent matching things that are already on their
    # own lines (those start/end with \n$$).
    text = re.sub(
        r'(?<!\$)\$\$([^$\n]+?)\$\$(?!\$)',
        lambda m: '\n\n$$\n' + m.group(1).strip() + '\n$$\n\n',
        text,
    )

    # ── 4. Ensure blank lines around standalone $$ delimiters ─────────────────
    # We track opener/closer state so we only add blanks in the right places:
    #   • opener $$ — needs blank line BEFORE it; formula follows immediately
    #   • closer $$ — formula ends immediately before it; needs blank line AFTER
    lines = text.split('\n')
    out: list[str] = []
    in_display = False

    for i, line in enumerate(lines):
        if line.strip() == '$$':
            if not in_display:
                # Opening delimiter
                if out and out[-1].strip():   # no blank line before → add one
                    out.append('')
                out.append(line)
                in_display = True
                # Do NOT insert blank after opener — formula follows immediately
            else:
                # Closing delimiter
                out.append(line)
                in_display = False
                # Add blank line after closer if next line has content
                if i + 1 < len(lines) and lines[i + 1].strip():
                    out.append('')
        else:
            out.append(line)

    # ── 5. Collapse excessive blank lines ────────────────────────────────────
    text = '\n'.join(out)
    text = re.sub(r'\n{4,}', '\n\n\n', text)

    return text
