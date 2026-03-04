"""
agents/local_summarizer.py  — AuraGraph offline fallback
Generates clean structured study notes from PDF text WITHOUT using any LLM API.

Design philosophy:
  - Produce READABLE, CLEAN markdown — never mangle math symbols
  - Preserve any formula lines as-is (wrapped in backtick code blocks)
  - Proficiency controls: how many top sentences per section, whether
    to include formula lines, and the preamble tone
  - Let the frontend (KaTeX via react-markdown) handle actual math rendering
"""

import re
from collections import Counter


# ─── Stop words ───────────────────────────────────────────────────────────────
_STOP = set(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might must can could to of in on at for by with from as it "
    "its this that these those and or but not so if then than when where which who "
    "what how all any each every no more most other some such into out up down over "
    "under also just only very well about after before during between through while "
    "we they he she you i".split()
)


# ─── Text cleaning ────────────────────────────────────────────────────────────
def _clean_pdf_text(text: str) -> str:
    """Remove common PDF extraction noise: page numbers, running headers, short junk lines."""
    noise = re.compile(
        r"^\s*("
        r"(lecture|lec|slide|unit|module|chapter|topic|week|session)\s*[\d\.\:]+.*"
        r"|page\s+\d+"
        r"|\d+\s*/\s*\d+"
        r"|copyright|all rights reserved|university|institute|dept\."
        r"|www\.|http|\.com|\.edu|\.org"
        r")\s*$",
        re.IGNORECASE
    )
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or len(stripped) < 4:
            lines.append("")
            continue
        if noise.match(stripped):
            continue
        # Fix merged words from PDF: "thisIs" → "this Is", "word.Next" → "word. Next"
        fixed = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', stripped)
        fixed = re.sub(r'([.!?])([A-Z])', r'\1 \2', fixed)
        lines.append(fixed)
    # Collapse 3+ blank lines
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return result.strip()


# ─── Section detection ────────────────────────────────────────────────────────
def _split_sections(text: str) -> list[tuple[str, str]]:
    """
    Detect headings heuristically. Returns [(heading, body), ...].
    Falls back to paragraph-based chunking.
    """
    heading_pat = re.compile(
        r"^([A-Z][A-Z0-9 ,\-:\'&\/]{2,50}|[A-Z][a-z][A-Za-z0-9 ,\-:\'&\/]{3,50})$",
        re.MULTILINE
    )
    noise_heading = re.compile(r"(lecture|slide|page|copyright|university|institute)", re.I)
    matches = [m for m in heading_pat.finditer(text) if not noise_heading.search(m.group(0))]

    if len(matches) >= 2:
        sections = []
        for i, m in enumerate(matches):
            heading = m.group(0).strip().title()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) > 50:
                sections.append((heading, body))
        if sections:
            return sections

    # Fallback: chunk paragraphs into ~600-char sections
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if len(p.strip()) > 60]
    merged, current = [], ""
    for para in paras:
        if current and len(current) + len(para) > 700:
            merged.append(current)
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
    if current:
        merged.append(current)
    return [(f"Section {i+1}", c) for i, c in enumerate(merged)]


# ─── Math line detection ──────────────────────────────────────────────────────
def _is_math_line(line: str) -> bool:
    """Detect lines that are primarily mathematical expressions."""
    l = line.strip()
    if not l or len(l) > 200:
        return False
    # Already has LaTeX markers
    if "$" in l or "\\frac" in l or "\\sum" in l:
        return True
    # Has operators and short tokens typical of formulas
    has_ops = bool(re.search(r'[=\+\-\*/\^]{1}', l))
    has_bracket_var = bool(re.search(r'[A-Za-z]\s*[\(\[]\s*[nkmt]\s*[\)\]]', l))
    word_count = len(l.split())
    alpha_ratio = sum(c.isalpha() for c in l) / max(len(l), 1)
    # Formula: short, has operators, not mostly prose
    if has_ops and word_count < 15 and alpha_ratio < 0.6:
        return True
    if has_bracket_var:
        return True
    return False


# ─── Sentence scoring (TF-IDF-like) ──────────────────────────────────────────
def _score_and_pick(sentences: list[str], k: int) -> list[str]:
    """Pick top-k most informative sentences in original order."""
    all_words = [w.lower() for s in sentences for w in re.findall(r'\b[a-zA-Z]{3,}\b', s) if w.lower() not in _STOP]
    freq = Counter(all_words)

    def score(s: str) -> float:
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', s) if w.lower() not in _STOP]
        if not words:
            return 0.0
        base = sum(freq[w] for w in words) / len(words)
        # Bonus for definition/key statements
        if re.search(r'\b(defined|definition|means|states|theorem|law|principle|formula|algorithm|property|given by)\b', s, re.I):
            base *= 1.6
        if re.search(r'\b(example|note|important|recall|remember)\b', s, re.I):
            base *= 1.3
        return base

    scored = sorted(enumerate(sentences), key=lambda x: -score(x[1]))
    top_indices = set(i for i, _ in scored[:k])
    return [s for i, s in enumerate(sentences) if i in top_indices]


def _split_sentences(text: str) -> list[str]:
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in raw if len(s.strip().split()) >= 4]


# ─── Exam tips ────────────────────────────────────────────────────────────────
def _exam_tip(heading: str, body: str) -> str:
    h, b = heading.lower(), body.lower()
    if re.search(r"theorem|transform|law|series|property", h + " " + b):
        return "State the theorem/definition precisely — examiners award marks for exact wording."
    if re.search(r"deriv|proof|show that|prove", b):
        return "Reproduce the derivation step-by-step — partial credit is given for correct intermediate steps."
    if re.search(r"formula|equation|expression|given by", b):
        return "Memorise the formula with all variable definitions — numerical problems are very common."
    if re.search(r"condition|constraint|valid|converge|region|require", b):
        return "Know and state the conditions/constraints — often 1–2 marks in exams."
    if re.search(r"application|used in|practical|real.world", b):
        return "Know at least 2 real-world applications — a common short-answer question."
    return "Write the definition first, then explain with an example for full marks."


# ─── Section builder ──────────────────────────────────────────────────────────
def _build_section(heading: str, body: str, prose_k: int, include_math: bool) -> str | None:
    lines = body.split("\n")
    math_lines, prose_lines = [], []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_math_line(stripped):
            math_lines.append(stripped)
        else:
            prose_lines.append(stripped)

    sentences = _split_sentences(" ".join(prose_lines))
    top_prose = _score_and_pick(sentences, prose_k) if sentences else []

    parts = []

    # High-value prose first
    if top_prose:
        parts.append("\n\n".join(top_prose))

    # Math / formulae (wrapped in code block to preserve symbols)
    if include_math and math_lines:
        for mline in math_lines[:4]:  # cap at 4 formula lines
            parts.append(f"`{mline}`")

    if not parts:
        return None

    tip = _exam_tip(heading, body)
    section_body = "\n\n".join(parts)
    return f"## {heading}\n\n{section_body}\n\n> 📝 **Exam Tip:** {tip}"


# ─── Proficiency config ───────────────────────────────────────────────────────
_PROF = {
    "Beginner":     {"prose_k": 6, "include_math": False, "max_sec": 14,
                     "label": "Conceptual focus — core ideas and analogies, formulas optional"},
    "Intermediate": {"prose_k": 4, "include_math": True,  "max_sec": 18,
                     "label": "Balanced depth — key formulas with explanation"},
    "Advanced":     {"prose_k": 2, "include_math": True,  "max_sec": 24,
                     "label": "Full depth — derivations, formulas, edge-case conditions"},
}


# ─── Public API ───────────────────────────────────────────────────────────────
def generate_local_note(slides_text: str, textbook_text: str, proficiency: str) -> str:
    """
    Generate a structured Markdown study note purely from extracted PDF text.
    No LLM, no regex math conversion — just clean extractive summarization.
    """
    cfg = _PROF.get(proficiency, _PROF["Intermediate"])
    prose_k    = cfg["prose_k"]
    incl_math  = cfg["include_math"]
    max_sec    = cfg["max_sec"]

    slides_text  = _clean_pdf_text(slides_text)
    textbook_text = _clean_pdf_text(textbook_text)

    sections: list[str] = []
    seen: set[str] = set()

    def add_sections(text: str, label_suffix: str = ""):
        for heading, body in _split_sections(text):
            if len(sections) >= max_sec:
                break
            key = re.sub(r"\s+", " ", heading.lower().strip())
            if key in seen:
                continue
            seen.add(key)
            sec = _build_section(heading + label_suffix, body, prose_k, incl_math)
            if sec:
                sections.append(sec)

    if slides_text:
        add_sections(slides_text)
    if textbook_text:
        add_sections(textbook_text, " *(Textbook)*")

    if not sections:
        return (
            "## ⚠️ Could Not Extract Notes\n\n"
            "No readable text was found in your PDFs. "
            "Make sure they are text-based (not scanned images).\n\n"
            "If they are scanned, use a tool like Adobe Acrobat to run OCR first."
        )

    header = (
        f"# AuraGraph Study Notes\n\n"
        f"*Proficiency: **{proficiency}** — {cfg['label']}*\n\n"
        f"> ⚠️ **Note:** These notes are generated by a local extractive summarizer "
        f"(no AI). For AI-enhanced notes with proper explanations and exam tips, "
        f"add your Azure OpenAI credentials to `backend/.env`.\n"
    )
    return header + "\n\n---\n\n" + "\n\n---\n\n".join(sections)
