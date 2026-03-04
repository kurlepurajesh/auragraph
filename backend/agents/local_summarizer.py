import re
from collections import Counter

_NOISE_LINE = re.compile(
    r"^\s*("
    r"(lecture|lec|slide|unit|module|chapter|topic|week|part|session)\s*[\d\.\:]+.*"
    r"|page\s+\d+"
    r"|\d+\s*/\s*\d+"
    r"|[A-Z]{2,10}\s*\d{3,}"
    r"|copyright|all rights reserved|university|institute|dept\.|department"
    r"|www\.|http|\.com|\.edu|\.org"
    r"|\d{4}\s*[-]\s*\d{4}"
    r")\s*$",
    re.IGNORECASE
)
_NOISE_SHORT = re.compile(r"^\s*[\d\.\-\*\u2022]+\s*$")

# ── PDF artifact Unicode cleanup ────────────────────────────────────────────
_PDF_ARTIFACTS = [
    ("\u25c6", " "),   # ◆ black diamond
    ("\u2666", " "),   # ♦ diamond suit
    ("\u2662", " "),   # ♢ white diamond
    ("\u22c4", " "),   # ⋄ diamond operator  (often mis-encoded sum/prod)
    ("\u25aa", " "),   # ▪ small square
    ("\u2022", " - "), # • bullet
    ("\u25e6", " - "), # ◦ white bullet
    ("\u2013", "-"),   # – en dash
    ("\u2014", " - "),  # — em dash
    ("\ufb01", "fi"),  # ﬁ ligature
    ("\ufb02", "fl"),  # ﬂ ligature
    ("\u2212", "-"),   # − minus sign
    ("\u00d7", "*"),   # × multiplication
    ("\u22c5", "*"),   # ⋅ dot product
]

def _normalize_unicode(text: str) -> str:
    for ch, repl in _PDF_ARTIFACTS:
        text = text.replace(ch, repl)
    return text

_MATH_SUBS = [
    (r"\bomega_0\b", r"$\\omega_0$"),
    (r"\bomega\b", r"$\\omega$"),
    (r"\balpha\b(?!\w)", r"$\\alpha$"),
    (r"\bbeta\b(?!\w)", r"$\\beta$"),
    (r"\bgamma\b(?!\w)", r"$\\gamma$"),
    (r"\bdelta\b(?!\w)", r"$\\delta$"),
    (r"\btheta\b(?!\w)", r"$\\theta$"),
    (r"\bphi\b(?!\w)", r"$\\phi$"),
    (r"\blambda\b(?!\w)", r"$\\lambda$"),
    (r"\bmu\b(?!\w)", r"$\\mu$"),
    (r"\bsigma\b(?!\w)", r"$\\sigma$"),
    (r"\btau\b(?!\w)", r"$\\tau$"),
    (r"\bzeta\b(?!\w)", r"$\\zeta$"),
    (r"\binfinity\b", r"$\\infty$"),
    (r"\bpi\b(?!\w)", r"$\\pi$"),
    (r"\bX\(z\)", r"$X(z)$"),
    (r"\bH\(z\)", r"$H(z)$"),
    (r"\bY\(z\)", r"$Y(z)$"),
    (r"\bX\(s\)", r"$X(s)$"),
    (r"\bH\(s\)", r"$H(s)$"),
    (r"\bconvolution\b", r"convolution ($*$)"),
    (r"\b([a-z])\[n\]", r"$\1[n]$"),
    (r"\b([a-z])\[k\]", r"$\1[k]$"),
    (r"\b([a-z])\[m\]", r"$\1[m]$"),
    (r"\bx\(t\)", r"$x(t)$"),
    (r"\by\(t\)", r"$y(t)$"),
    (r"\bh\(t\)", r"$h(t)$"),
    (r"\be\^(j[\w\\]+)", r"$e^{\1}$"),
    (r"\b([A-Za-z])\^(-?\d+)", r"$\1^{\2}$"),
]

def _reconstruct_math(text):
    if "$" in text:
        return text
    for pat, repl in _MATH_SUBS:
        try:
            text = re.sub(pat, repl, text)
        except Exception:
            pass
    return text

def _fix_spaces(text: str) -> str:
    """Re-insert spaces that PDF extraction dropped."""
    # Normalize unicode artifacts first
    text = _normalize_unicode(text)
    # Split camelCase: discreteRandom -> discrete Random
    text = re.sub(r'([a-z\d])([A-Z])', r'\1 \2', text)
    # Space after sentence-ending punctuation: "value.If" -> "value. If"
    text = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', text)
    # Space after comma/period/semicolon missing: "a,b" -> "a, b"
    text = re.sub(r'([.,;:])([A-Za-z\d])', r'\1 \2', text)
    # Number immediately followed by letter that starts a var: "1eitqi" → "1 e itqi"
    text = re.sub(r'(\d)([a-df-hj-np-z])', r'\1 \2', text)  # skip 'e' (scientific notation)
    return text

def _clean_text(text):
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if _NOISE_LINE.match(stripped):
            continue
        if _NOISE_SHORT.match(stripped):
            continue
        if len(stripped) < 4:
            continue
        cleaned.append(_fix_spaces(line))
    text2 = "\n".join(cleaned)
    text2 = re.sub(r"\n{3,}", "\n\n", text2)
    return text2.strip()

def _split_sections(text):
    heading_pat = re.compile(
        r"^([A-Z][A-Z0-9 ,\-:\'&\/]{2,60}|[A-Z][a-z][A-Za-z0-9 ,\-:\'&\/]{3,55})$",
        re.MULTILINE
    )
    matches = [m for m in heading_pat.finditer(text) if not _NOISE_LINE.match(m.group(0))]
    sections = []
    if len(matches) >= 2:
        for i, m in enumerate(matches):
            heading = m.group(0).strip().title()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) > 30:
                sections.append((heading, body))
        if sections:
            return sections
    chunks = [c.strip() for c in re.split(r"\n{2,}", text) if len(c.strip()) > 60]
    merged, current = [], ""
    for chunk in chunks:
        if len(current) + len(chunk) < 800:
            current += ("\n\n" if current else "") + chunk
        else:
            if current:
                merged.append(current)
            current = chunk
    if current:
        merged.append(current)
    return [(f"Section {i+1}", c) for i, c in enumerate(merged)]

def _has_math(text):
    # If the line has very long runs without spaces (merged prose from PDF),
    # it is NOT a math line even if it contains = signs
    stripped = text.strip()
    tokens = stripped.split()
    if tokens:
        max_token_len = max(len(t) for t in tokens)
        alpha_ratio = sum(c.isalpha() for c in stripped) / max(len(stripped), 1)
        # Long all-alpha token = merged words: "LetXbeadiscrete..."
        if max_token_len > 18 and alpha_ratio > 0.6:
            return False
    # Reject lines that are more than 70% alphabetic with no real math operators
    real_ops = re.findall(r'[=<>\^\+\-\*/\\\{\}\(\)\[\]]', stripped)
    alpha_chars = sum(c.isalpha() for c in stripped)
    if alpha_chars > 0 and len(real_ops) / max(alpha_chars, 1) < 0.03 and alpha_chars > 25:
        return False
    return bool(re.search(
        r'[=\^\u222b\u2211\u220f\u221a\u00b1\u221e\u2202\u2207\u2264\u2265\u2200]|'
        r'[A-Za-z]\s*[=<>]\s*[A-Za-z0-9(]|'
        r'\b(sin|cos|tan|exp|log|lim|max|min|det|sum|integral)\b|'
        r'\b[a-z][\(\[]\s*[nktmz]\s*[\)\]]',
        text
    ))

def _classify_line(line):
    l = line.strip().lower()
    if _has_math(line): return "formula"
    if re.search(r"\b(defined as|definition:|is called|referred to as|denoted by|means that)\b", l): return "definition"
    if re.search(r"\b(proof:|derive|derivation|show that|we have|therefore|hence|thus|substituting)\b", l): return "derivation"
    if re.search(r"\b(example:|e\.g\.|for instance|consider|suppose|case [0-9])\b", l): return "example"
    if re.search(r"\b(note:|important:|recall:|key point:|remember:|caution:)\b", l): return "note"
    if re.search(r"\b(theorem:|lemma:|corollary:|proposition:|property:)\b", l): return "theorem"
    return "body"

_STOP = set("a an the is are was were be been being have has had do does did will would shall should may might must can could to of in on at for by with from as it its this that these those and or but not so if then than when where which who what how all any each every no more most other some such into out up down over under also just only very well about after before during between through while i we they he she you".split())

def _compress_body(body, max_words=320, keep_derivations=True):
    lines = [l.rstrip() for l in body.split("\n")]
    formula_lines, prose_lines = [], []
    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        k = _classify_line(stripped)
        if k in ("formula", "definition", "theorem", "note", "example"):
            formula_lines.append((stripped, k))
        elif k == "derivation":
            if keep_derivations:
                formula_lines.append((stripped, k))
            # else skip derivation lines (Beginner mode)
        else:
            prose_lines.append(stripped)
    all_words = [w.lower() for s in prose_lines for w in re.findall(r"\b[a-zA-Z]{3,}\b", s) if w.lower() not in _STOP]
    freq = Counter(all_words)
    def score(s):
        words = [w.lower() for w in re.findall(r"\b[a-zA-Z]{3,}\b", s) if w.lower() not in _STOP]
        return sum(freq[w] for w in words) / (len(words) + 1)
    top_prose = set(sorted(prose_lines, key=score, reverse=True)[:max(6, len(prose_lines) // 3)])
    result = list(formula_lines)
    word_count = sum(len(fl.split()) for fl, _ in formula_lines)
    for sentence in prose_lines:
        if sentence in top_prose:
            wc = len(sentence.split())
            if word_count + wc <= max_words:
                result.append((sentence, "body"))
                word_count += wc
    line_order = {l.strip(): i for i, l in enumerate(lines) if l.strip()}
    result.sort(key=lambda x: line_order.get(x[0], 9999))
    return result

def _to_latex_line(text: str) -> str:
    """Convert a raw math line to a KaTeX display block."""
    t = text.strip()
    if t.startswith("$$") and t.endswith("$$"):
        return t
    t2 = t.replace("$", "").strip()

    # --- Safety check: if line has 3+ English prose words, don't wrap in $$ ---
    words = t2.split()
    alpha_word_count = sum(
        1 for w in words
        if re.match(r'^[a-zA-Z]{4,}$', w.rstrip('.,;:!?'))
    )
    if alpha_word_count >= 3:
        # Mixed prose+math line — render as plain text with inline subs
        return _reconstruct_math(t2)

    # --- Don't wrap lines with unbalanced brackets (incomplete piecewise lines) ---
    opens = t2.count('(') + t2.count('{') + t2.count('[')
    closes = t2.count(')') + t2.count('}') + t2.count(']')
    if opens != closes:
        return _reconstruct_math(t2)

    # --- LaTeX keyword replacements ---
    replacements = [
        (r"\bsum\b", r"\\sum"),
        (r"\bprod\b", r"\\prod"),
        (r"\binfty\b|\binfinity\b", r"\\infty"),
        (r"\bomega_0\b", r"\\omega_0"),
        (r"\bomega\b", r"\\omega"),
        (r"\balpha\b", r"\\alpha"),
        (r"\bbeta\b", r"\\beta"),
        (r"\bgamma\b", r"\\gamma"),
        (r"\bdelta\b", r"\\delta"),
        (r"\btheta\b", r"\\theta"),
        (r"\bphi\b", r"\\phi"),
        (r"\blambda\b", r"\\lambda"),
        (r"\bmu\b", r"\\mu"),
        (r"\bsigma\b", r"\\sigma"),
        (r"\btau\b", r"\\tau"),
        (r"\bzeta\b", r"\\zeta"),
        (r"\bpi\b", r"\\pi"),
        (r"\bsin\b", r"\\sin"),
        (r"\bcos\b", r"\\cos"),
        (r"\btan\b", r"\\tan"),
        (r"\bexp\b", r"\\exp"),
        (r"\blog\b", r"\\log"),
        (r"\blim\b", r"\\lim"),
        (r"\bmax\b", r"\\max"),
        (r"\bmin\b", r"\\min"),
        (r"\bdet\b", r"\\det"),
        (r"([A-Za-z])\^(-?\d+)", r"\1^{\2}"),
        (r"([A-Za-z])_(-?\d+|[a-z])", r"\1_{\2}"),
        (r"<=", r"\\leq"),
        (r">=", r"\\geq"),
        (r"!=", r"\\neq"),
    ]
    for pat, repl in replacements:
        try:
            t2 = re.sub(pat, repl, t2)
        except Exception:
            pass
    return f"$$\n{t2}\n$$"


def _format_compressed(compressed):
    output = []
    formula_buffer = []

    def flush_formulas():
        if not formula_buffer:
            return
        converted = []
        for f in formula_buffer:
            result = _to_latex_line(f)
            # If _to_latex_line returned a $$ block, extract its inner content
            if result.startswith("$$\n") and result.endswith("\n$$"):
                converted.append(result[3:-3].strip())
            else:
                # It was demoted to prose — output directly
                output.append(result)
                output.append("")
                formula_buffer.clear()
                return
        if len(converted) == 1:
            output.append(f"$$\n{converted[0]}\n$$")
        else:
            # Multiple math lines: join with LaTeX line-break \\
            output.append("$$\n" + " \\\\\n".join(converted) + "\n$$")
        output.append("")
        formula_buffer.clear()

    for line, kind in compressed:
        stripped = line.strip()
        if kind == "formula":
            formula_buffer.append(stripped)
        else:
            flush_formulas()
            # Apply inline math reconstruction to prose lines
            stripped = _reconstruct_math(stripped)
            if kind in ("definition", "theorem"):
                output.append(f"**{stripped}**")
            elif kind == "note":
                output.append(f"> {stripped}")
            elif kind == "example":
                output.append(f"*{stripped}*")
            else:
                output.append(stripped)

    flush_formulas()
    return "\n".join(output).strip()

def _exam_tips(heading, body):
    b, h = body.lower(), heading.lower()
    tips = []
    if re.search(r"theorem|transform|law|property|series", h + " " + b):
        tips.append("State the theorem/law precisely — examiners award marks for exact wording.")
    if re.search(r"deriv|proof|show that|prove", b):
        tips.append("Reproduce the derivation step-by-step — partial credit given for correct intermediate steps.")
    if re.search(r"formula|equation|expression|given by", b) or _has_math(body):
        tips.append("Memorise the formula and each variable — numerical application questions are very common.")
    if re.search(r"condition|constraint|valid|converge|region|require", b):
        tips.append("Know the conditions under which this applies.")
    if re.search(r"application|used in|practical|real.world", b):
        tips.append("Know at least 2 real-world applications — a common 2-mark question.")
    return tips[:2] if tips else ["Write the definition first, then explain."]

MAX_SECTIONS = 22

# Proficiency config: (max_words, keep_derivations, prose_keep_ratio_divisor, section_limit)
_PROF_CONFIG = {
    "Beginner":      dict(max_words=520, keep_derivations=False, prose_div=2, sec_limit=18),
    "Intermediate":  dict(max_words=340, keep_derivations=True,  prose_div=3, sec_limit=22),
    "Advanced":      dict(max_words=180, keep_derivations=True,  prose_div=5, sec_limit=22),
}

def _prof_preamble(proficiency, heading):
    """Return a short tailored intro line for a section based on proficiency."""
    if proficiency == "Beginner":
        return f"> 💬 **Beginner focus:** Understand what this means conceptually before studying the formulas.\n"
    if proficiency == "Advanced":
        return f"> ⚡ **Advanced:** Derivations, edge cases and rigorous conditions are included.\n"
    return ""  # Intermediate — no preamble

def generate_local_note(slides_text, textbook_text, proficiency):
    slides_text = _clean_text(slides_text)
    textbook_text = _clean_text(textbook_text)

    cfg = _PROF_CONFIG.get(proficiency, _PROF_CONFIG["Intermediate"])
    max_words      = cfg["max_words"]
    keep_deriv     = cfg["keep_derivations"]
    sec_limit      = cfg["sec_limit"]

    output_sections = []
    seen_headings = set()

    if slides_text.strip():
        for heading, body in _split_sections(slides_text):
            if len(output_sections) >= sec_limit: break
            h_key = re.sub(r"\s+", " ", heading.lower().strip())
            if h_key in seen_headings: continue
            seen_headings.add(h_key)
            preamble = _prof_preamble(proficiency, heading)
            formatted = _format_compressed(_compress_body(body, max_words, keep_deriv))
            if not formatted.strip(): continue
            tips = _exam_tips(heading, body)
            tip_block = "\n".join(f"> \U0001f4dd **Exam Tip:** {t}" for t in tips)
            output_sections.append(f"## {heading}\n\n{preamble}{formatted}\n\n{tip_block}")

    if textbook_text.strip():
        # Textbook sections get slightly fewer words than slides
        tb_max_words = max(120, max_words - 60)
        for heading, body in _split_sections(textbook_text):
            if len(output_sections) >= sec_limit: break
            h_key = re.sub(r"\s+", " ", heading.lower().strip())
            if h_key in seen_headings: continue
            seen_headings.add(h_key)
            preamble = _prof_preamble(proficiency, heading)
            formatted = _format_compressed(_compress_body(body, tb_max_words, keep_deriv))
            if not formatted.strip(): continue
            tips = _exam_tips(heading, body)
            tip_block = "\n".join(f"> \U0001f4dd **Exam Tip:** {t}" for t in tips)
            output_sections.append(f"## {heading} *(Textbook)*\n\n{preamble}{formatted}\n\n{tip_block}")

    if not output_sections:
        return "## Note\n\nCould not extract text. Ensure PDFs are text-based (not scanned)."

    _prof_labels = {
        "Beginner":     "Conceptual focus \u2014 core ideas and worked examples",
        "Intermediate": "Balanced depth \u2014 formulas and key derivations",
        "Advanced":     "Full depth \u2014 derivations, edge cases and rigorous conditions",
    }
    prof_label = _prof_labels.get(proficiency, "Balanced depth")
    header = (
        f"# AuraGraph Study Notes\n"
        f"*Proficiency: **{proficiency}*** \u2014 {prof_label}\n"
    )
    return header + "\n\n---\n\n" + "\n\n---\n\n".join(output_sections)
