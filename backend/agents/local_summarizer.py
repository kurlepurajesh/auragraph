r"""
agents/local_summarizer.py  — AuraGraph offline fallback  v2.0
Generates rich, structured study notes from raw PDF / PPTX text WITHOUT any LLM.

KEY IMPROVEMENTS OVER v1
────────────────────────
1. SLIDE-FIRST architecture: slides drive the section structure.
   The textbook is used ONLY to enrich slide sections — never to add new
   sections that the professor didn't cover.  This kills the "too much book
   content" problem.

2. SMART MATH DETECTION: two-pass approach.
   Pass 1 — structural math (already-formatted LaTeX, equations on own lines).
   Pass 2 — Greek-keyword lines that look like formulas, not prose.
   Prose sentences containing Greek letters (e.g. "Let alpha be the learning
   rate") are now kept as prose instead of being wrongly converted to $$…$$.

3. LEAN TEXTBOOK ENRICHMENT: for each slide-section we look for the single
   most relevant textbook paragraph (keyword overlap).
   We add at most 2-3 sentences of context — not the whole textbook chapter.

4. PAGING: returns clean ## headings; frontend splits on \n## for one page
   per concept.

5. MATH RENDERING: All $$…$$ blocks are emitted with blank lines before and
   after so remark-math / rehype-katex renders them correctly.
"""

import re
from collections import Counter
from typing import Optional


# ─── Stop words ───────────────────────────────────────────────────────────────
_STOP = set(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might must can could to of in on at for by with from as it "
    "its this that these those and or but not so if then than when where which who "
    "what how all any each every no more most other some such into out up down over "
    "under also just only very well about after before during between through while "
    "we they he she you i".split()
)


# ─── Math symbol → LaTeX conversion table ─────────────────────────────────────
# IMPORTANT ordering: longer / more-specific patterns FIRST to avoid partial matches.
# Each Greek letter appears EXACTLY ONCE.
_MATH_SUBS = [
    # Special combos (longest first)
    (r'\b2pi\b',                  r'2\\pi'),
    (r'\bj2pi\b',                 r'j2\\pi'),
    (r'\bpi\s*/\s*2\b',           r'\\pi/2'),
    (r'\bC\((\w+),\s*(\w+)\)',    r'\\binom{\1}{\2}'),

    # Greek letters (capitalized first, then lowercase)
    (r'\bGamma\b',    r'\\Gamma'),
    (r'\bgamma\b',    r'\\gamma'),
    (r'\bDelta\b',    r'\\Delta'),
    (r'\bdelta\b',    r'\\delta'),
    (r'\bTheta\b',    r'\\Theta'),
    (r'\btheta\b',    r'\\theta'),
    (r'\bLambda\b',   r'\\Lambda'),
    (r'\blambda\b',   r'\\lambda'),
    (r'\bSigma\b',    r'\\Sigma'),
    (r'\bsigma\b',    r'\\sigma'),
    (r'\bOmega\b',    r'\\Omega'),
    (r'\bomega\b',    r'\\omega'),
    (r'\bAlpha\b',    r'\\Alpha'),
    (r'\balpha\b',    r'\\alpha'),
    (r'\bBeta\b',     r'\\Beta'),
    (r'\bbeta\b',     r'\\beta'),
    (r'\bepsilon\b',  r'\\epsilon'),
    (r'\bvarepsilon\b', r'\\varepsilon'),
    (r'\bzeta\b',     r'\\zeta'),
    # eta: only standalone (not the suffix of beta/theta/etc)
    (r'(?<![a-z])eta\b', r'\\eta'),
    (r'\bmu\b',       r'\\mu'),
    (r'\bnu\b',       r'\\nu'),
    (r'\bxi\b',       r'\\xi'),
    (r'\bPi\b',       r'\\Pi'),
    (r'\bpi\b',       r'\\pi'),
    (r'\brho\b',      r'\\rho'),
    (r'\btau\b',      r'\\tau'),
    (r'\bPhi\b',      r'\\Phi'),
    (r'\bphi\b',      r'\\phi'),
    (r'\bPsi\b',      r'\\Psi'),
    (r'\bpsi\b',      r'\\psi'),
    (r'\bnabla\b',    r'\\nabla'),
    (r'\bchi\b',      r'\\chi'),
    (r'\bkappa\b',    r'\\kappa'),

    # Constants / special symbols
    (r'\binfty\b',       r'\\infty'),
    (r'\binfinity\b',    r'\\infty'),
    (r'\bforall\b',      r'\\forall'),
    (r'\bexists\b',      r'\\exists'),

    # Calculus / analysis
    (r'\bintegral(?=\b|_|\^|\{|\s)', r'\\int'),
    (r'\bpartial\b',     r'\\partial'),
    (r'\bgrad\b',        r'\\nabla'),
    (r'\bsqrt(?=[\s_^\{(])', r'\\sqrt'),

    # Summation / product
    (r'\bsum(?=\b|_|\^|\{)',    r'\\sum'),
    (r'\bprod(?=\b|_|\^|\{)',   r'\\prod'),

    # Limits
    (r'\blim(?=\b|_|\^|\{)',    r'\\lim'),
    (r'\bmax(?=\b|_|\^|\{)',    r'\\max'),
    (r'\bmin(?=\b|_|\^|\{)',    r'\\min'),
    (r'\bsup(?=\b|_|\^|\{)',    r'\\sup'),
    (r'\binf(?=\b|_|\^|\{)',    r'\\inf'),

    # Trig / hyperbolic / log
    (r'\bsinh(?=\b|_|\^|\{)',   r'\\sinh'),
    (r'\bcosh(?=\b|_|\^|\{)',   r'\\cosh'),
    (r'\btanh(?=\b|_|\^|\{)',   r'\\tanh'),
    (r'\bsin(?=\b|_|\^|\{)',    r'\\sin'),
    (r'\bcos(?=\b|_|\^|\{)',    r'\\cos'),
    (r'\btan(?=\b|_|\^|\{)',    r'\\tan'),
    (r'\bcot(?=\b|_|\^|\{)',    r'\\cot'),
    (r'\bsec(?=\b|_|\^|\{)',    r'\\sec'),
    (r'\bcsc(?=\b|_|\^|\{)',    r'\\csc'),
    (r'\blog(?=\b|_|\^|\{)',    r'\\log'),
    (r'\bln(?=\b|_|\^|\{)',     r'\\ln'),
    (r'\bexp(?=\b|_|\^|\{)',    r'\\exp'),
    (r'\bdet(?=\b|_|\^|\{)',    r'\\det'),
    (r'\btr\b',                 r'\\text{tr}'),

    # Arrows
    (r'<->',  r'\\leftrightarrow'),
    (r'<=>',  r'\\Leftrightarrow'),
    (r'->',   r'\\rightarrow'),
    (r'=>',   r'\\Rightarrow'),
    (r'<-',   r'\\leftarrow'),

    # Relations
    (r'!=',           r'\\neq'),
    (r'>=',           r'\\geq'),
    (r'<=',           r'\\leq'),
    (r'\bapprox\b',   r'\\approx'),
    (r'\bpm\b',       r'\\pm'),
    (r'\btimes\b',    r'\\times'),
    (r'\bcdot\b',     r'\\cdot'),
]


def _raw_to_latex(raw: str) -> str:
    r"""Convert a raw PDF formula string to proper LaTeX (single-pass, no double-backslash)."""
    s = raw.strip()
    if '\\' in s:   # already has LaTeX — don't double-convert
        return s

    # Build a single combined pattern: alternation of all patterns in order.
    # The first alternative that matches at each position wins (Python re is
    # leftmost-first), and the engine advances past the match so it cannot
    # re-match the same text.
    combined_pattern = '|'.join(f'(?P<g{i}>{pat})' for i, (pat, _) in enumerate(_MATH_SUBS))
    repls = [r for _, r in _MATH_SUBS]

    def _replace(m: re.Match) -> str:
        # Find which group matched and return its replacement directly.
        # Note: we cannot call re.sub(pat, repl, matched_text) here because
        # lookahead patterns (e.g. r'\bsqrt(?=[\s_^\{(])') strip the lookahead
        # context from the captured group, causing the re-applied pattern to fail.
        for i, repl in enumerate(repls):
            gname = f'g{i}'
            if m.group(gname) is not None:
                return repl
        return m.group(0)

    return re.sub(combined_pattern, _replace, s)


# ─── Math line detection (two-pass) ───────────────────────────────────────────
_STRUCTURAL_MATH_RE = re.compile(
    r'\\[a-zA-Z]+'           # already has LaTeX command
    r'|\$[^$]|\$\$'          # already wrapped in $
    r'|[A-Za-z]\s*\^\s*[\d{(]'   # exponent x^2, e^{-t}
    r'|[A-Za-z]\s*_\s*[\d{(a-z]' # subscript x_n, H_0
    r'|\b\d+\s*[+\-*/]\s*\d+\b'  # pure arithmetic 2+3
)

_PROSE_GUARD_RE = re.compile(
    r'\b(is|are|the|denotes|means|where|which|such|called|represent|equal|'
    r'defined|given|known|refers|describes|consider|let|suppose|note|show|'
    r'when|thus|hence|since|because|therefore|allows|using|used)\b',
    re.I
)

_GREEK_RE = re.compile(
    r'\b(alpha|beta|gamma|delta|epsilon|zeta|theta|lambda|mu|nu|xi|rho|sigma|tau|'
    r'phi|psi|omega|nabla|infty|infinity|integral|partial|chi|kappa)\b',
    re.I
)


def _is_math_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 300:
        return False

    # Pass 1: structural signals (always math regardless of prose words)
    if _STRUCTURAL_MATH_RE.search(s):
        if len(s.split()) > 12 and _PROSE_GUARD_RE.search(s):
            return False
        return True

    # Pass 2: Greek keyword + operator — raised limit to 12 words (was 8)
    has_ops   = bool(re.search(r'[=+\-*/^<>]', s))
    has_greek = bool(_GREEK_RE.search(s))
    if has_greek and has_ops:
        if len(s.split()) <= 12 and not _PROSE_GUARD_RE.search(s):
            return True

    # Pass 3: function notation with operator — catches "y(t) = x(t)*h(t) ..."
    # Pattern: identifier(anything) = ... with no prose guard words
    if re.search(r'[A-Za-z]\w*\s*\([^)]{0,20}\)\s*=', s):
        if not _PROSE_GUARD_RE.search(s):
            return True

    # Pass 4: very short purely symbolic lines
    if len(s.split()) <= 5 and re.search(r'[=+\-*/^]', s) and not re.search(r'\b(is|are|the|a|an)\b', s, re.I):
        return True

    return False


# ─── Text cleaning ────────────────────────────────────────────────────────────
_CID_INLINE_RE = re.compile(r'\(cid:\d+\)')
_PAGE_MARK_RE  = re.compile(r'---\s*[Pp]age\s+\d+\s*---')


def _clean_pdf_text(text: str) -> str:
    _noise = re.compile(
        r"^\s*("
        r"(lecture|lec|slide|unit|module|chapter|topic|week|session)\s*[\d\.\:]+.*"
        r"|page\s+\d+"
        r"|\d+\s*/\s*\d+"
        r"|copyright|all rights reserved|university|institute|dept\."
        r"|www\.|http|\.com|\.edu|\.org"
        r")\s*$",
        re.IGNORECASE
    )
    text = _CID_INLINE_RE.sub('', text)
    text = _PAGE_MARK_RE.sub('', text)

    lines: list[str] = []
    prev_compact = ''
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            prev_compact = ''
            continue
        if len(stripped) <= 3:
            continue
        if _noise.match(stripped):
            continue
        compact = re.sub(r'\s+', '', stripped)
        if compact and compact == prev_compact:
            fixed_cur = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', stripped)
            fixed_cur = re.sub(r'([.!?])([A-Z])', r'\1 \2', fixed_cur)
            if lines and lines[-1].strip():
                lines[-1] = fixed_cur
            continue
        prev_compact = compact if compact else prev_compact

        fixed = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', stripped)
        fixed = re.sub(r'([.!?])([A-Z])', r'\1 \2', fixed)
        lines.append(fixed)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ─── Slide-aware section parser ────────────────────────────────────────────────
def _parse_slide_sections(slides_text: str) -> list[tuple[str, str]]:
    """Parse slide text into (heading, body) pairs using slide markers."""
    slide_marker = re.compile(
        r'^---\s*Slide\s+\d+(?::\s*(.+?))?\s*---\s*$',
        re.MULTILINE
    )
    matches = list(slide_marker.finditer(slides_text))
    if matches:
        raw_sections = []
        for i, m in enumerate(matches):
            title = (m.group(1) or '').strip()
            start = m.end()
            end   = matches[i + 1].start() if i + 1 < len(matches) else len(slides_text)
            body  = slides_text[start:end].strip()
            raw_sections.append((title or f"Slide {i+1}", body))

        # Merge very short slides forward into the NEXT substantive slide.
        # Strategy: accumulate a buffer; when we hit a slide with real content,
        # prepend everything buffered before it.
        # "Short" = body < 80 chars AND the slide has no meaningful title.
        merged = []
        pending_bodies: list[str] = []   # short slide bodies waiting to attach

        for title, body in raw_sections:
            is_short = len(body) < 80 and (not title or title.startswith('Slide '))
            if is_short:
                # Buffer this content to prepend to the next slide
                if body:
                    pending_bodies.append(body)
            else:
                # Substantive slide — attach any pending content first
                if pending_bodies:
                    combined = "\n\n".join(pending_bodies) + "\n\n" + body
                    body = combined.strip()
                    pending_bodies = []
                merged.append((title, body))

        # Flush any remaining pending content into the last section
        if pending_bodies and merged:
            prev_t, prev_b = merged[-1]
            extra = "\n\n".join(pending_bodies)
            merged[-1] = (prev_t, (prev_b + "\n\n" + extra).strip())
        elif pending_bodies:
            # All slides were short — keep them as one section
            merged.append(("Overview", "\n\n".join(pending_bodies)))

        if merged:
            return merged

    return _detect_heading_sections(slides_text)


def _detect_heading_sections(text: str) -> list[tuple[str, str]]:
    heading_pat = re.compile(
        r"^("
        r"[A-Z][A-Z0-9 ,\-:\'&\/]{2,50}"
        r"|[A-Z][a-zA-Z0-9\-]+(?:\s+[A-Z][a-zA-Z0-9\-]+){1,6}"
        r"|\d+[\.\d]*\s+[A-Z][A-Za-z0-9 ,\-:\'&\/]{3,50}"
        r")$",
        re.MULTILINE
    )
    noise_h = re.compile(r"(lecture|slide|page|copyright|university|institute)", re.I)
    matches = [m for m in heading_pat.finditer(text) if not noise_h.search(m.group(0))]

    if len(matches) >= 2:
        secs = []
        for i, m in enumerate(matches):
            heading = m.group(0).strip().title()
            start   = m.end()
            end     = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body    = text[start:end].strip()
            if len(body) > 40:
                secs.append((heading, body))
        if secs:
            return secs

    paras   = [p.strip() for p in re.split(r"\n{2,}", text) if len(p.strip()) > 60]
    merged, current = [], ""
    for para in paras:
        if current and len(current) + len(para) > 800:
            merged.append(current)
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
    if current:
        merged.append(current)
    return [(f"Section {i+1}", c) for i, c in enumerate(merged)]


# ─── TF-IDF keyword extraction for textbook matching ─────────────────────────
def _keywords(text: str) -> set[str]:
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return {w for w in words if w not in _STOP}


def _keyword_overlap(a_kw: set[str], b_kw: set[str]) -> float:
    if not a_kw or not b_kw:
        return 0.0
    return len(a_kw & b_kw) / len(a_kw | b_kw)


def _find_best_textbook_paragraph(
    slide_heading: str,
    slide_body: str,
    textbook_paragraphs: list[str],
    min_overlap: float = 0.08,
) -> Optional[str]:
    slide_kw   = _keywords(slide_heading + " " + slide_body)
    best_score = min_overlap
    best_para  = None
    for para in textbook_paragraphs:
        if len(para) < 50:   # was 100 — too aggressive, dropped relevant short paragraphs
            continue
        para_kw = _keywords(para)
        score   = _keyword_overlap(slide_kw, para_kw)
        if score > best_score:
            best_score = score
            best_para  = para
    return best_para


def _extract_enrichment(textbook_para: str, max_sentences: int = 3) -> str:
    sentences = _split_sentences(textbook_para)
    if not sentences:
        return ""
    scored = []
    for s in sentences:
        score = 0
        if re.search(r'\b(defined|definition|theorem|states|formula|given by|'
                     r'represents|equals|describes|can be written)\b', s, re.I):
            score += 3
        if re.search(r'\b(because|therefore|since|hence|thus|this means)\b', s, re.I):
            score += 2
        if re.search(r'\b(important|key|fundamental|note|recall)\b', s, re.I):
            score += 1
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return " ".join(s for _, s in scored[:max_sentences])


# ─── Sentence utilities ────────────────────────────────────────────────────────
def _split_sentences(text: str) -> list[str]:
    protected = re.sub(
        r'\b(Fig|Eq|No|Vol|Ch|Sec|Ref|est|approx|vs|etc|e\.g|i\.e|Dr|Prof|St|Mr|Mrs|Ms)\.',
        lambda m: m.group(0).replace('.', '\x00'),
        text
    )
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z])', protected)
    restored = [s.replace('\x00', '.').strip() for s in raw]
    return [s for s in restored if len(s.split()) >= 5 and not _is_math_line(s)]


def _score_and_pick(sentences: list[str], k: int) -> list[str]:
    all_words = [
        w.lower() for s in sentences
        for w in re.findall(r'\b[a-zA-Z]{3,}\b', s)
        if w.lower() not in _STOP
    ]
    freq = Counter(all_words)

    def score(s: str) -> float:
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', s) if w.lower() not in _STOP]
        if not words:
            return 0.0
        base = sum(freq[w] for w in words) / len(words)
        if re.search(r'\b(defined|definition|means|states|theorem|law|principle|formula|'
                     r'algorithm|property|given by|represents|equals|describes)\b', s, re.I):
            base *= 2.0
        if re.search(r'\b(example|instance|consider|such as|for example|e\.g|imagine)\b', s, re.I):
            base *= 1.5
        if re.search(r'\b(because|therefore|since|hence|thus|which means|this means)\b', s, re.I):
            base *= 1.4
        if re.search(r'\b(important|note|recall|remember|key|fundamental|essential|crucial)\b', s, re.I):
            base *= 1.3
        return base

    scored   = sorted(enumerate(sentences), key=lambda x: -score(x[1]))
    top_idx  = {i for i, _ in scored[:k]}
    return [s for i, s in enumerate(sentences) if i in top_idx]


# ─── Math line extraction from body text ──────────────────────────────────────
def _extract_math_and_prose(body: str) -> tuple[list[str], list[str]]:
    math_set   = []
    math_seen  = set()
    prose_lines = []
    for line in body.split("\n"):
        s = line.strip()
        if not s:
            continue
        if _is_math_line(s):
            key = re.sub(r'\s+', '', s.lower())
            if key not in math_seen:
                math_seen.add(key)
                math_set.append(s)
        else:
            prose_lines.append(s)
    return math_set, prose_lines


# ─── Real-world analogy bank ──────────────────────────────────────────────────
_ANALOGIES: dict[str, str] = {
    "fourier": (
        "🎵 **Think of it like this:** Imagine holding a cable connected to a speaker playing a chord. "
        "You hear *one* complex sound. The Fourier Transform is like a **musical equaliser** — it splits "
        "that complex sound into individual frequency ingredients. After the transform you can see exactly "
        "*how much* of each frequency is present."
    ),
    "convolution": (
        "🌊 **Think of it like this:** Imagine pouring water through a sponge. The sponge is the system's "
        "**impulse response** $h(t)$. The water is your **input signal** $x(t)$. Convolution calculates "
        "the smearing effect — at every moment it asks: 'How much past input is still ringing through the system?'"
    ),
    "laplace": (
        "🔧 **Think of it like this:** Fourier only works on stable signals. Laplace multiplies the signal "
        "by $e^{-\\sigma t}$ to tame it before transforming. Think of Laplace as "
        "**Fourier with a safety harness** for unstable or transient signals."
    ),
    "z-transform": (
        "🎮 **Think of it like this:** All digital audio is processed as discrete number sequences. "
        "The Z-Transform analyses these **digital sequences** the same way Laplace analyses continuous signals. "
        "Laplace = analog world; Z-Transform = **digital world**."
    ),
    "sampling": (
        "📱 **Think of it like this:** Recording audio at 44,100 Hz means 44,100 measurements per second. "
        "Nyquist says you must sample at **at least twice** the highest frequency you want to capture. "
        "Sample too slowly and you get **aliasing** — distorted high frequencies."
    ),
    "lti": (
        "🏭 **Think of it like this:** An LTI system is like a reliable factory machine. **Linear**: "
        "double the input → double the output. **Time-invariant**: the machine behaves identically "
        "whether you feed it input now or an hour later."
    ),
    "probability": (
        "🎲 **Think of it like this:** If a bag has 3 red and 7 blue balls, the probability of picking "
        "red is 3/10 = 0.3. Everything in probability builds on: "
        "$P(\\text{event}) = \\frac{\\text{favourable}}{\\text{total outcomes}}$."
    ),
    "binomial": (
        "🪙 **Think of it like this:** Flip a biased coin $n$ times. The Binomial distribution answers "
        "'What's the chance of exactly $k$ heads?' The formula $\\binom{n}{k} p^k (1-p)^{n-k}$ counts "
        "all ways to arrange $k$ successes in $n$ tries."
    ),
    "normal": (
        "📈 **Think of it like this:** Measure 10,000 people's heights — most cluster near the average "
        "with fewer at extremes. That bell curve is the Normal distribution, appearing everywhere due to "
        "the **Central Limit Theorem**."
    ),
    "derivative": (
        "🚗 **Think of it like this:** A car's **speedometer** shows velocity — that's a derivative. "
        "It tells you how fast your *position* is changing at this exact instant. "
        "Geometrically, it's the **slope of the tangent line** at a point."
    ),
    "integral": (
        "📦 **Think of it like this:** Imagine filling a pool by tracking flow rate each second. "
        "The integral adds all those tiny amounts to give the **total water collected**. "
        "$\\int_a^b f(x)\\,dx$ = area under the curve from $a$ to $b$."
    ),
    "eigenvalue": (
        "🔍 **Think of it like this:** Apply a transformation to every vector. Most change direction. "
        "But special **eigenvectors** only get stretched/shrunk, keeping the same direction. "
        "The stretch factor is the **eigenvalue** $\\lambda$."
    ),
    "matrix": (
        "📊 **Think of it like this:** A matrix encodes a **transformation** — rotating, scaling, "
        "reflecting a space. Multiplying a vector by a matrix applies that transformation to it."
    ),
}


def _get_analogy(heading: str, body: str) -> str:
    text = (heading + " " + body).lower()
    for kw, analogy in _ANALOGIES.items():
        if kw in text:
            return analogy
    return ""


# ─── Formula plain-English explainer ─────────────────────────────────────────
_FORMULA_HINTS: list[tuple[str, str]] = [
    (r'\\int',       "↑ This integral sums up tiny contributions over a range — the continuous version of adding things up."),
    (r'\\sum',       "↑ Σ means: add up the expression for every value from the bottom index to the top."),
    (r'e\^',         "↑ $e^x$ is the exponential function ($e \\approx 2.718$). It grows or decays very fast."),
    (r'\\frac',      "↑ This fraction: divide the top (numerator) by the bottom (denominator)."),
    (r'\\binom',     "↑ $\\binom{n}{k}$ = 'n choose k' — ways to pick $k$ items from $n$."),
    (r'\\partial',   "↑ ∂ is a partial derivative — how the function changes when only ONE variable changes."),
    (r'j.*\\omega|\\omega.*j', "↑ $j = \\sqrt{-1}$. $j\\omega$ represents a pure oscillation at frequency $\\omega$."),
    (r'\\nabla',     "↑ ∇ (nabla/gradient) points in the direction of steepest increase."),
    (r'\\sqrt',      "↑ $\\sqrt{x}$ is the square root — the value that, squared, gives $x$."),
]


def _formula_hint(latex_line: str) -> str:
    for pattern, hint in _FORMULA_HINTS:
        if re.search(pattern, latex_line):
            return hint
    return ""


# ─── Exam tips ────────────────────────────────────────────────────────────────
def _exam_tip(heading: str, body: str) -> str:
    h, b = heading.lower(), body.lower()
    if re.search(r"theorem|transform|law|series|property", h + " " + b):
        return "State the theorem/definition precisely — examiners award marks for exact wording."
    if re.search(r"deriv|proof|show that|prove", b):
        return "Reproduce the derivation step-by-step — partial credit for each correct intermediate step."
    if re.search(r"formula|equation|expression|given by", b):
        return "Memorise the formula with all variable definitions — numerical application problems are very common."
    if re.search(r"condition|constraint|valid|converge|region|require", b):
        return "Know and state ALL conditions/constraints — often worth 1–2 dedicated marks."
    if re.search(r"application|used in|practical|real.world", b):
        return "Know at least 2–3 real-world applications — a common short-answer question."
    return "Write the formal definition first, then explain it in your own words, then give a worked example."


# ─── Format a math block ──────────────────────────────────────────────────────
def _math_block(raw_line: str) -> str:
    """Emit a display math block with proper blank-line padding for remark-math."""
    latex = _raw_to_latex(raw_line)
    return f"\n$$\n{latex}\n$$\n"


# ─── Section builders ─────────────────────────────────────────────────────────
def _build_beginner_section(
    heading: str, body: str, enrichment: str,
    sentences: list[str], math_lines: list[str],
) -> Optional[str]:
    if not sentences and not math_lines:
        return None

    enrich_sentences = _split_sentences(enrichment) if enrichment else []
    all_sentences = sentences + [s for s in enrich_sentences if s not in sentences]

    defn_s    = [s for s in all_sentences if re.search(r'\b(is|are|defined|means|represents|refers to|known as|called|describes)\b', s, re.I)]
    why_s     = [s for s in all_sentences if re.search(r'\b(used|useful|important|application|allows|enables|helps|purpose|essential|fundamental)\b', s, re.I)]
    how_s     = [s for s in all_sentences if re.search(r'\b(given by|calculated|computed|found by|steps|process|method|procedure|approach|first|then|finally)\b', s, re.I)]
    example_s = [s for s in all_sentences if re.search(r'\b(example|instance|consider|suppose|imagine|such as|for example|e\.g|think of)\b', s, re.I)]
    reason_s  = [s for s in all_sentences if re.search(r'\b(because|therefore|since|hence|thus|which means|this means|this is why|reason)\b', s, re.I)]

    parts = []

    what_pool = defn_s[:4] if defn_s else all_sentences[:3]
    parts.append("### 📖 What Is It?\n\n" + "\n\n".join(what_pool[:4]))

    why_pool = list(dict.fromkeys(why_s + reason_s))
    if why_pool:
        parts.append("### 🎯 Why Does It Matter?\n\n" + "\n\n".join(why_pool[:3]))

    shown    = set(what_pool[:4] + why_pool[:3])
    how_pool = how_s if how_s else [s for s in all_sentences if s not in shown]
    if how_pool:
        parts.append("### ⚙️ How Does It Work?\n\n" + "\n\n".join(how_pool[:4]))

    if example_s:
        parts.append("### 💎 Worked Example\n\n" + "\n\n".join(example_s[:2]))

    analogy = _get_analogy(heading, body)
    if analogy:
        parts.append(f"> {analogy}")

    all_shown = set(what_pool[:4] + why_pool[:3] + how_pool[:4] + example_s[:2])
    leftover  = [s for s in all_sentences if s not in all_shown]
    if leftover:
        parts.append("### 📌 Also Important\n\n" + "\n\n".join(leftover[:3]))

    if math_lines:
        formula_parts = ["> 💡 **Formulas** (shown for reference — focus on the idea first!)\n"]
        for ml in math_lines[:4]:
            formula_parts.append(_math_block(ml))
            hint = _formula_hint(_raw_to_latex(ml))
            if hint:
                formula_parts.append(f"*{hint}*")
        parts.append("\n\n".join(formula_parts))

    if not parts:
        return None

    tip = _exam_tip(heading, body)
    return f"## {heading}\n\n" + "\n\n".join(parts) + f"\n\n> 📝 **Exam Tip:** {tip}"


def _build_intermediate_section(
    heading: str, body: str, enrichment: str,
    top_prose: list[str], math_lines: list[str],
) -> Optional[str]:
    if not top_prose and not math_lines:
        return None

    enrich_sentences = _split_sentences(enrichment)[:2] if enrichment else []
    parts = []

    defn = [s for s in top_prose if re.search(
        r'\b(is|are|defined as|defined by|means|represents|refers to|describes|known as|called)\b', s, re.I)]
    if defn:
        parts.append("### 📖 Definition\n\n" + " ".join(defn[:2]))

    how = [s for s in top_prose if s not in defn and re.search(
        r'\b(given by|calculated|computes|maps|transforms|yields|produces|allows|enables|because|therefore|hence|since|which means)\b', s, re.I)]
    if not how:
        how = [s for s in top_prose if s not in defn]
    combined_how = list(dict.fromkeys(how[:3] + enrich_sentences))
    if combined_how:
        parts.append("### 💡 Intuition\n\n" + "\n\n".join(combined_how[:4]))

    analogy = _get_analogy(heading, body)
    if analogy:
        parts.append(f"> {analogy}")

    cond = [s for s in top_prose if s not in defn and s not in how and re.search(
        r'\b(condition|constraint|requirement|valid|converge|exist|property|must|only if|if and only|assume)\b', s, re.I)]
    if cond:
        bullets = "\n".join(f"- {s}" for s in cond[:4])
        parts.append(f"### 📋 Key Conditions\n\n{bullets}")

    if math_lines:
        formula_parts = ["### 🔢 Formulas\n"]
        for ml in math_lines[:5]:
            formula_parts.append(_math_block(ml))
        parts.append("\n\n".join(formula_parts))

    if not parts:
        return None

    tip = _exam_tip(heading, body)
    return f"## {heading}\n\n" + "\n\n".join(parts) + f"\n\n> 📝 **Exam Tip:** {tip}"


def _build_advanced_section(
    heading: str, body: str, enrichment: str,
    top_prose: list[str], math_lines: list[str],
) -> Optional[str]:
    if not top_prose and not math_lines:
        return None

    enrich_sentences = _split_sentences(enrichment)[:2] if enrichment else []
    parts = []

    defn = [s for s in top_prose if re.search(
        r'\b(is defined|defined as|formally|let|suppose|assume|denote|given|theorem|states that)\b', s, re.I)]
    rest = [s for s in top_prose if s not in defn]
    all_prose = list(dict.fromkeys(rest + enrich_sentences))

    if defn:
        parts.append("### Formal Definition\n\n" + " ".join(defn[:3]))
    if all_prose:
        paras = []
        for i in range(0, len(all_prose), 3):
            paras.append(" ".join(all_prose[i:i+3]))
        parts.append("\n\n".join(paras))

    if math_lines:
        formula_block = [_math_block(ml) for ml in math_lines[:8]]
        parts.append("\n\n".join(formula_block))

    cond = [s for s in top_prose if re.search(
        r'\b(condition|constraint|converge|exist|valid|boundary|special case|edge case|degenerate|when|if and only)\b', s, re.I)]
    if cond:
        bullets = "\n".join(f"- {s}" for s in cond[:6])
        parts.append(f"### Conditions & Edge Cases\n\n{bullets}")

    if not parts:
        return None

    tip = _exam_tip(heading, body)
    return f"## {heading}\n\n" + "\n\n".join(parts) + f"\n\n> 📝 **Exam Tip:** {tip}"


# ─── Main section dispatcher ──────────────────────────────────────────────────
def _build_section(
    heading: str, body: str, enrichment: str,
    prose_k: int, proficiency: str,
) -> Optional[str]:
    math_lines, prose_lines = _extract_math_and_prose(body)
    sentences = _split_sentences(" ".join(prose_lines))

    if not sentences and not math_lines:
        return None

    if proficiency == "Foundations":
        return _build_beginner_section(heading, body, enrichment, sentences, math_lines)
    else:
        top_prose = _score_and_pick(sentences, prose_k) if len(sentences) > prose_k else sentences
        if proficiency == "Practitioner":
            return _build_intermediate_section(heading, body, enrichment, top_prose, math_lines)
        else:
            return _build_advanced_section(heading, body, enrichment, top_prose, math_lines)


# ─── Proficiency config ───────────────────────────────────────────────────────
_PROF = {
    "Foundations": {
        "prose_k": 99,
        "label":   "Full conceptual depth — every idea explained from scratch with analogies",
    },
    "Practitioner": {
        "prose_k": 8,
        "label":   "Balanced depth — key formulas with intuition and application",
    },
    "Expert": {
        "prose_k": 6,
        "label":   "Full rigour — formal definitions, derivations, edge cases",
    },
}


# ─── Public API ───────────────────────────────────────────────────────────────
def generate_local_note(slides_text: str, textbook_text: str, proficiency: str) -> str:
    """
    Generate structured Markdown study notes from extracted PDF/PPTX text.

    v2 Architecture:
      1. Parse slides into sections — SLIDES DRIVE the note structure.
      2. Split textbook into paragraphs.
      3. For each slide section, find the single most relevant textbook
         paragraph (keyword overlap). Extract 2-3 enrichment sentences.
      4. Build the section note: slide content + minimal enrichment.
      5. Deduplicate headings.
    """
    cfg     = _PROF.get(proficiency, _PROF["Practitioner"])
    prose_k = cfg["prose_k"]

    slides_text   = _clean_pdf_text(slides_text)
    textbook_text = _clean_pdf_text(textbook_text)

    # 1. Parse slide sections
    slide_sections = _parse_slide_sections(slides_text) if slides_text.strip() else []

    # 2. If no slides, use textbook as primary source (no enrichment)
    if not slide_sections and textbook_text.strip():
        slide_sections = _detect_heading_sections(textbook_text)
        textbook_text  = ""

    if not slide_sections:
        return (
            "## ⚠️ Could Not Extract Notes\n\n"
            "No readable text was found in your PDFs. "
            "Make sure they are text-based (not scanned images).\n\n"
            "If they are scanned, use a tool like Adobe Acrobat to run OCR first."
        )

    # 3. Split textbook into paragraphs for enrichment matching
    textbook_paragraphs: list[str] = []
    if textbook_text.strip():
        textbook_paragraphs = [
            p.strip()
            for p in re.split(r'\n{2,}', textbook_text)
            if len(p.strip()) > 60   # was 120 — too aggressive, dropped short but relevant paragraphs
        ]

    # 4. Build sections
    sections: list[str] = []
    seen_keys: set[str] = set()

    for heading, body in slide_sections:
        key = re.sub(r'\s+', ' ', heading.lower().strip())
        if key in seen_keys:
            continue
        seen_keys.add(key)

        enrichment = ""
        if textbook_paragraphs:
            best_para = _find_best_textbook_paragraph(heading, body, textbook_paragraphs)
            if best_para:
                enrichment = _extract_enrichment(
                    best_para,
                    max_sentences=3 if proficiency == "Foundations" else 2
                )

        sec = _build_section(heading, body, enrichment, prose_k, proficiency)
        if sec:
            sections.append(sec)

    if not sections:
        return (
            "## ⚠️ Could Not Extract Notes\n\n"
            "No readable text was found in your PDFs. "
            "Make sure they are text-based (not scanned images)."
        )

    # 5. Compose final output
    level_banner = {
        "Foundations":  "🔰 **Foundations mode** — Every concept taught from scratch. Read each section fully before looking at formulas.",
        "Practitioner": "⚡ **Practitioner mode** — Key definitions, formulas, and worked intuition.",
        "Expert":       "🎯 **Expert mode** — Full rigour: derivations, edge cases, formal notation.",
    }.get(proficiency, "")

    header = (
        f"# AuraGraph Study Notes\n\n"
        f"**Study Mode: {proficiency}** — {cfg['label']}\n\n"
        f"> {level_banner}\n"
    )
    return header + "\n\n---\n\n" + "\n\n---\n\n".join(sections)
