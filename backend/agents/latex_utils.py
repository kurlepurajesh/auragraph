"""
agents/latex_utils.py
Utility: normalize all LaTeX delimiter variants to $ / $$ (rehype-katex friendly).

Taken from the emergent branch and extended for our codebase.
Any AI-generated text may use \\[ \\] or \\( \\) — this converter normalizes them.
"""

import re


def fix_latex_delimiters(text: str) -> str:
    """
    Convert all LaTeX delimiter variants to $ / $$ that rehype-katex understands.

    Handles:
      - \\[ ... \\]  →  $$\\n...\\n$$
      - \\( ... \\)  →  $ ... $
      - [ formula ]  at start of a line → $$ formula $$
      - Cleans up blank lines inside $$ blocks
    """
    # Fix display math: \\[ ... \\] -> $$ ... $$
    text = re.sub(r'\\\[\s*', '\n$$\n', text)
    text = re.sub(r'\s*\\\]', '\n$$\n', text)

    # Fix inline math: \\( ... \\) -> $ ... $
    text = re.sub(r'\\\(\s*', ' $', text)
    text = re.sub(r'\s*\\\)', '$ ', text)

    # Fix bare bracket math: [ formula ] at start of line (common AI output)
    text = re.sub(r'^\[\s*(.+?)\s*\]\s*$', r'$$ \1 $$', text, flags=re.MULTILINE)

    # Clean up doubled $$ on same line
    text = re.sub(r'\$\$\s*\$\$', '$$', text)

    # Remove blank lines inside $$ display blocks
    lines = text.split('\n')
    result = []
    in_display = False
    for line in lines:
        stripped = line.strip()
        if stripped == '$$':
            in_display = not in_display
            result.append(line)
        elif in_display and stripped == '':
            continue  # skip blank lines inside display math
        else:
            result.append(line)

    return '\n'.join(result)
