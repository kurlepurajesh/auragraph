import re
from collections import Counter

_STOP = set(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might must can could to of in on at for by with from as it "
    "its this that these those and or but not so if then than when where which who "
    "what how all any each every no more most other some such into out up down over "
    "under also just only very well about after before during between through while "
    "we they he she you i".split()
)


def _clean_pdf_text(text):
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
        fixed = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', stripped)
        fixed = re.sub(r'([.!?])([A-Z])', r'\1 \2', fixed)
        lines.append(fixed)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _split_sections(text):
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


def _is_math_line(line):
    l = line.strip()
    if not l or len(l) > 200:
        return False
    if "$" in l or "\\frac" in l or "\\sum" in l:
        return True
    has_ops = bool(re.search(r'[=\+\-\*/\^]{1}', l))
    word_count = len(l.split())
    alpha_ratio = sum(c.isalpha() for c in l) / max(len(l), 1)
    if has_ops and word_count < 15 and alpha_ratio < 0.6:
        return True
    return False


def _score_and_pick(sentences, k):
    all_words = [w.lower() for s in sentences for w in re.findall(r'\b[a-zA-Z]{3,}\b', s) if w.lower() not in _STOP]
    freq = Counter(all_words)

    def score(s):
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', s) if w.lower() not in _STOP]
        if not words:
            return 0.0
        base = sum(freq[w] for w in words) / len(words)
        if re.search(r'\b(defined|definition|means|states|theorem|law|principle|formula|algorithm|property|given by)\b', s, re.I):
            base *= 1.6
        if re.search(r'\b(example|note|important|recall|remember)\b', s, re.I):
            base *= 1.3
        return base

    scored = sorted(enumerate(sentences), key=lambda x: -score(x[1]))
    top_indices = set(i for i, _ in scored[:k])
    return [s for i, s in enumerate(sentences) if i in top_indices]


def _split_sentences(text):
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in raw if len(s.strip().split()) >= 4]


def _exam_tip(heading, body):
    h, b = heading.lower(), body.lower()
    if re.search(r"theorem|transform|law|series|property", h + " " + b):
        return "State the theorem/definition precisely - examiners award marks for exact wording."
    if re.search(r"deriv|proof|show that|prove", b):
        return "Reproduce the derivation step-by-step - partial credit is given for correct intermediate steps."
    if re.search(r"formula|equation|expression|given by", b):
        return "Memorise the formula with all variable definitions - numerical problems are very common."
    return "Write the definition first, then explain with an example for full marks."


def _build_section(heading, body, prose_k, include_math, is_beginner):
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
    if not sentences:
        return None
    top_prose = _score_and_pick(sentences, prose_k)
    parts = []
    if is_beginner:
        parts.append(f"**Core Concept:** {top_prose[0]}" if top_prose else "")
        if len(top_prose) > 1:
            parts.append("**Intuition:** " + top_prose[1])
        if len(top_prose) > 2:
            parts.append("\n\n".join(top_prose[2:]))
    else:
        parts.append("\n\n".join(top_prose))
    if include_math and math_lines:
        for mline in math_lines[:4]:
            parts.append(f"$$\n{mline}\n$$")
    if not parts:
        return None
    tip = _exam_tip(heading, body)
    section_body = "\n\n".join(parts)
    return f"## {heading}\n\n{section_body}\n\n> **Exam Tip:** {tip}"


_PROF = {
    "Beginner": {"prose_k": 8, "include_math": True, "max_sec": 30, "is_beginner": True, "label": "Detailed & beginner-friendly"},
    "Intermediate": {"prose_k": 8, "include_math": True, "max_sec": 30, "is_beginner": False, "label": "Balanced depth"},
    "Advanced": {"prose_k": 10, "include_math": True, "max_sec": 40, "is_beginner": False, "label": "Full depth"},
}


def generate_local_note(slides_text, textbook_text, proficiency):
    cfg = _PROF.get(proficiency, _PROF["Intermediate"])
    prose_k = cfg["prose_k"]
    incl_math = cfg["include_math"]
    max_sec = cfg["max_sec"]
    is_beginner = cfg["is_beginner"]
    slides_text = _clean_pdf_text(slides_text)
    textbook_text = _clean_pdf_text(textbook_text)
    sections = []
    seen = set()

    def add_sections(text, label_suffix=""):
        for heading, body in _split_sections(text):
            if len(sections) >= max_sec:
                break
            key = re.sub(r"\s+", " ", heading.lower().strip())
            if key in seen:
                continue
            seen.add(key)
            sec = _build_section(heading + label_suffix, body, prose_k, incl_math, is_beginner)
            if sec:
                sections.append(sec)

    if slides_text:
        add_sections(slides_text)
    if textbook_text:
        add_sections(textbook_text, " *(Textbook)*")

    if not sections:
        return "## Could Not Extract Notes\n\nNo readable text found. Make sure PDFs are text-based."

    header = f"# AuraGraph Study Notes\n\n*Proficiency: **{proficiency}** - {cfg['label']}*\n"
    return header + "\n\n---\n\n" + "\n\n---\n\n".join(sections)
