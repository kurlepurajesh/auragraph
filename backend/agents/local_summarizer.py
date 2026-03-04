r"""
agents/local_summarizer.py  — AuraGraph offline fallback
Generates rich, structured study notes from raw PDF text WITHOUT any LLM API.

Core philosophy:
  - Beginner  = LONGEST, RICHEST notes. Every concept taught from scratch:
                What is it? → Why does it matter? → Real-world analogy →
                How does it work (step by step)? → Formula explained in words → Exam tip.
                prose_k is highest because beginners need ALL the content.
  - Intermediate = Definition + formula + application. Balanced.
  - Advanced = Dense: formal definition + derivation + edge cases. Fewer prose
                sentences needed because each one is information-dense.

Math symbols:
  - Raw PDF text like "integral", "sigma", "omega", "nabla" are converted
    to proper LaTeX (\int, \sigma, \omega, \nabla) BEFORE being wrapped in $$
  - This is the only way KaTeX can render them correctly
  - Beginner notes SHOW formulas but add a plain-English explanation line below each
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


# ─── Math symbol → LaTeX conversion table ─────────────────────────────────────
# Applied to every detected formula line BEFORE wrapping in $$...$$.
# Order matters: multi-word / longer patterns come before single-word ones.
_MATH_SUBS = [
    # ── Special combos first ──────────────────────────────────────────────────
    (r'\b2pi\b',             r'2\\pi'),
    (r'\bj2pi\b',            r'j2\\pi'),
    (r'\bpi\s*/\s*2\b',      r'\\pi/2'),
    # Fraction written as a/b  →  \frac{a}{b}  (only for simple token/token)
    (r'\bC\((\w+),\s*(\w+)\)', r'\\binom{\1}{\2}'),   # C(n,k) → \binom{n}{k}

    # ── Greek letters ─────────────────────────────────────────────────────────
    (r'\balpha\b',            r'\\alpha'),
    (r'\bbeta\b',             r'\\beta'),
    (r'\bgamma\b',            r'\\gamma'),
    (r'\bGamma\b',            r'\\Gamma'),
    (r'\bdelta\b',            r'\\delta'),
    (r'\bDelta\b',            r'\\Delta'),
    (r'\bepsilon\b',          r'\\epsilon'),
    (r'\bzeta\b',             r'\\zeta'),
    (r'\beta\b',              r'\\eta'),
    (r'\btheta\b',            r'\\theta'),
    (r'\bTheta\b',            r'\\Theta'),
    (r'\blambda\b',           r'\\lambda'),
    (r'\bLambda\b',           r'\\Lambda'),
    (r'\bmu\b',               r'\\mu'),
    (r'\bnu\b',               r'\\nu'),
    (r'\bxi\b',               r'\\xi'),
    (r'\bpi\b',               r'\\pi'),
    (r'\bPi\b',               r'\\Pi'),
    (r'\brho\b',              r'\\rho'),
    (r'\bsigma\b',            r'\\sigma'),
    (r'\bSigma\b',            r'\\Sigma'),
    (r'\btau\b',              r'\\tau'),
    (r'\bphi\b',              r'\\phi'),
    (r'\bPhi\b',              r'\\Phi'),
    (r'\bpsi\b',              r'\\psi'),
    (r'\bPsi\b',              r'\\Psi'),
    (r'\bomega\b',            r'\\omega'),
    (r'\bOmega\b',            r'\\Omega'),
    (r'\bnabla\b',            r'\\nabla'),

    # ── Constants / special symbols ───────────────────────────────────────────
    (r'\binfty\b',            r'\\infty'),
    (r'\binfinity\b',         r'\\infty'),

    # ── Calculus / analysis operators ─────────────────────────────────────────
    (r'\bintegral\b',         r'\\int'),
    (r'\bpartial\b',          r'\\partial'),
    (r'\bsqrt\b',             r'\\sqrt'),
    (r'\bgrad\b',             r'\\nabla'),

    # ── Summation / product ───────────────────────────────────────────────────
    (r'\bsum\b',              r'\\sum'),
    (r'\bprod\b',             r'\\prod'),

    # ── Limits / standard functions ───────────────────────────────────────────
    (r'\blim\b',              r'\\lim'),
    (r'\bmax\b',              r'\\max'),
    (r'\bmin\b',              r'\\min'),
    (r'\bsup\b',              r'\\sup'),
    (r'\binf\b',              r'\\inf'),
    (r'\bsin\b',              r'\\sin'),
    (r'\bcos\b',              r'\\cos'),
    (r'\btan\b',              r'\\tan'),
    (r'\bcot\b',              r'\\cot'),
    (r'\bsec\b',              r'\\sec'),
    (r'\bcsc\b',              r'\\csc'),
    (r'\bsinh\b',             r'\\sinh'),
    (r'\bcosh\b',             r'\\cosh'),
    (r'\btanh\b',             r'\\tanh'),
    (r'\blog\b',              r'\\log'),
    (r'\bln\b',               r'\\ln'),
    (r'\bexp\b',              r'\\exp'),
    (r'\bdet\b',              r'\\det'),
    (r'\btr\b',               r'\\text{tr}'),

    # ── Arrows ────────────────────────────────────────────────────────────────
    (r'<->',                  r'\\leftrightarrow'),
    (r'<=>',                  r'\\Leftrightarrow'),
    (r'->',                   r'\\rightarrow'),
    (r'=>',                   r'\\Rightarrow'),
    (r'<-',                   r'\\leftarrow'),

    # ── Relations ─────────────────────────────────────────────────────────────
    (r'!=',                   r'\\neq'),
    (r'>=',                   r'\\geq'),
    (r'<=',                   r'\\leq'),
    (r'\bapprox\b',           r'\\approx'),
    (r'\bpm\b',               r'\\pm'),
    (r'\btimes\b',            r'\\times'),
    (r'\bcdot\b',             r'\\cdot'),
]


def _raw_to_latex(raw: str) -> str:
    """Convert a raw PDF formula string into proper LaTeX for use inside $$...$$."""
    s = raw.strip()
    for pattern, repl in _MATH_SUBS:
        s = re.sub(pattern, repl, s)
    return s


# ─── Math line detection ──────────────────────────────────────────────────────
# A line is treated as a formula if it looks like math, not prose.
_GREEK_RAW = re.compile(
    r'\b(alpha|beta|gamma|delta|epsilon|zeta|theta|lambda|mu|nu|xi|rho|sigma|tau|'
    r'phi|psi|omega|nabla|infty|infinity|integral|partial|sqrt)\b',
    re.I
)


def _is_math_line(line: str) -> bool:
    l = line.strip()
    if not l or len(l) > 250:
        return False
    # Already has LaTeX markers
    if re.search(r'\\[a-zA-Z]+|\$', l):
        return True
    # Raw greek / math keyword in a short-ish line
    if _GREEK_RAW.search(l) and len(l.split()) < 20:
        return True
    has_ops    = bool(re.search(r'[=\+\-\*/\^]', l))
    has_bv     = bool(re.search(r'[A-Za-z]\s*[\(\[]\s*[nkmt\d]\s*[\)\]]', l))
    wc         = len(l.split())
    alpha_r    = sum(c.isalpha() for c in l) / max(len(l), 1)
    if has_ops and wc < 15 and alpha_r < 0.60:
        return True
    if has_bv:
        return True
    return False


# ─── Text cleaning ────────────────────────────────────────────────────────────
def _clean_pdf_text(text: str) -> str:
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


# ─── Section detection ────────────────────────────────────────────────────────
def _split_sections(text: str) -> list[tuple[str, str]]:
    heading_pat = re.compile(
        r"^([A-Z][A-Z0-9 ,\-:\'&\/]{2,50}|[A-Z][a-z][A-Za-z0-9 ,\-:\'&\/]{3,50})$",
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
            if len(body) > 50:
                secs.append((heading, body))
        if secs:
            return secs

    # Fallback: chunk by paragraphs
    paras   = [p.strip() for p in re.split(r"\n{2,}", text) if len(p.strip()) > 60]
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


# ─── Sentence scoring ─────────────────────────────────────────────────────────
def _split_sentences(text: str) -> list[str]:
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    # Filter out sentences that are actually math lines misclassified as prose
    return [s.strip() for s in raw
            if len(s.strip().split()) >= 5 and not _is_math_line(s.strip())]


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
        if re.search(r'\b(because|therefore|since|hence|thus|which means|this means|'
                     r'in other words|this is why)\b', s, re.I):
            base *= 1.4
        if re.search(r'\b(important|note|recall|remember|key|fundamental|essential|crucial)\b', s, re.I):
            base *= 1.3
        return base

    scored     = sorted(enumerate(sentences), key=lambda x: -score(x[1]))
    top_idx    = set(i for i, _ in scored[:k])
    return [s for i, s in enumerate(sentences) if i in top_idx]


# ─── Real-world analogy bank ──────────────────────────────────────────────────
# These are injected into Beginner sections when a keyword matches.
_ANALOGIES: dict[str, str] = {
    "fourier": (
        "🎵 **Think of it like this:** Imagine you're holding a raw audio cable connected to "
        "a speaker playing a chord. You can hear *one* complex sound. The Fourier Transform is "
        "like a **musical equaliser** — it splits that one complex sound into individual notes "
        "(frequencies: bass, mid, treble). After the transform, you can see exactly *how much* "
        "of each frequency is present. That's all it does to any signal — it reveals the "
        "hidden frequency ingredients inside it."
    ),
    "convolution": (
        "🌊 **Think of it like this:** Imagine pouring water through a sponge. The sponge "
        "represents the system's **impulse response** $h(t)$. The water poured in is your "
        "**input signal** $x(t)$. As the water passes through, the sponge smears and delays it "
        "in a specific way. Convolution calculates that exact smearing effect — at every moment "
        "in time, it asks: 'How much of the past input is still ringing through the system right now?'"
    ),
    "laplace": (
        "🔧 **Think of it like this:** The Fourier Transform only works on signals that don't "
        "blow up over time (stable signals). But what if you need to analyse a circuit that's "
        "just been switched on, or a rocket engine ramping up exponentially? That's where Laplace "
        "steps in — it multiplies the signal by $e^{-\\sigma t}$ to tame it before transforming. "
        "Think of Laplace as **Fourier with a safety harness** for unstable signals."
    ),
    "z-transform": (
        "🎮 **Think of it like this:** All digital audio (Spotify, YouTube, your phone) is "
        "processed as sequences of numbers sampled at fixed time steps (1, 2, 3, 4...). "
        "The Z-Transform is the tool that analyses these **digital sequences** the same way "
        "Laplace analyses continuous real-world signals. If Laplace = the analog world tool, "
        "Z-Transform = the **digital world tool**."
    ),
    "sampling": (
        "📱 **Think of it like this:** When you record audio on your phone at 44,100 Hz, "
        "it takes 44,100 measurements per second. The Nyquist Theorem says you must sample "
        "at **at least twice** the highest frequency you want to capture. Human hearing tops "
        "out at ~20,000 Hz, so 44,100 Hz sampling is just enough. If you sample slower, "
        "high-frequency sounds get distorted — this is called **aliasing**."
    ),
    "lti": (
        "🏭 **Think of it like this:** An LTI system is like a reliable machine on a factory "
        "line. **Linear** means: if you double the input, the output doubles. If you add two "
        "inputs, the outputs add. **Time-invariant** means: the machine behaves the same "
        "whether you feed it input now or an hour from now. Most real engineering systems "
        "(filters, amplifiers, circuits) are designed to be LTI."
    ),
    "probability": (
        "🎲 **Think of it like this:** Probability is just a formal way of measuring "
        "*how likely* an event is. If a bag has 3 red and 7 blue balls, the probability "
        "of picking red is 3/10 = 0.3, or 30%. Everything in probability theory builds "
        "on this: $P(\\text{event}) = \\frac{\\text{favourable outcomes}}{\\text{total outcomes}}$."
    ),
    "binomial": (
        "🪙 **Think of it like this:** Flip a biased coin $n$ times independently. "
        "The Binomial distribution answers: 'What's the chance of getting exactly $k$ heads?' "
        "Each flip is identical and independent — that's the key condition. "
        "The formula $\\binom{n}{k} p^k (1-p)^{n-k}$ counts all the ways to arrange "
        "$k$ successes in $n$ tries, then multiplies by the probability of each arrangement."
    ),
    "normal": (
        "📈 **Think of it like this:** Measure the heights of 10,000 people. Most cluster "
        "near the average (mean $\\mu$), with fewer and fewer people as you go taller or shorter. "
        "That bell-shaped curve is the Normal distribution. It appears everywhere in nature and "
        "engineering because of the **Central Limit Theorem** — averages of random things always "
        "tend toward a Normal distribution, no matter what the original distribution was."
    ),
    "derivative": (
        "🚗 **Think of it like this:** Your car's **speedometer** shows velocity. "
        "That's a derivative — it tells you how fast your *position* is changing at this "
        "exact instant. A derivative $f'(x)$ measures the instantaneous rate of change of "
        "$f$ at $x$. Geometrically, it's the **slope of the tangent line** at that point. "
        "If $f'(x) > 0$, the function is increasing there. If $f'(x) < 0$, it's decreasing."
    ),
    "integral": (
        "📦 **Think of it like this:** Imagine filling a swimming pool by tracking how fast "
        "water flows in each second. The integral adds up all those tiny flow amounts over time "
        "to give you the **total water collected**. More generally, $\\int_a^b f(x)\\,dx$ "
        "computes the **area under the curve** $f(x)$ from $a$ to $b$ — the accumulation of "
        "infinitely many infinitely thin slices."
    ),
    "eigenvalue": (
        "🔍 **Think of it like this:** Apply a transformation (like rotating + stretching "
        "a rubber sheet) to every vector. Most vectors change direction. But a few special "
        "vectors only get **stretched or shrunk** — they keep pointing the same way. "
        "Those are **eigenvectors**. The stretch factor is the **eigenvalue** $\\lambda$. "
        "Google's PageRank literally finds the dominant eigenvector of the web link matrix "
        "to rank pages!"
    ),
    "matrix": (
        "📊 **Think of it like this:** A matrix is a table of numbers that encodes a "
        "**transformation** — rotating, scaling, reflecting, or shearing a space. "
        "When you multiply a vector by a matrix, you're applying that transformation to it. "
        "Multiplying two matrices chains two transformations together. "
        "This is why matrices are fundamental to computer graphics, machine learning, and physics."
    ),
}


def _get_analogy(heading: str, body: str) -> str:
    """Return the best matching analogy for a section, or empty string."""
    text = (heading + " " + body).lower()
    for kw, analogy in _ANALOGIES.items():
        if kw in text:
            return analogy
    return ""


# ─── Formula plain-English explainer ─────────────────────────────────────────
# For Beginner mode: add a human-readable line below each formula.
_FORMULA_HINTS: list[tuple[str, str]] = [
    (r'\\int',                "↑ This integral sums up tiny contributions over a range — it's the continuous version of adding things up."),
    (r'\\sum',                "↑ This sigma (Σ) means: add up the expression for every value from the bottom number to the top."),
    (r'e\^',                  "↑ $e^x$ is the exponential function. $e \\approx 2.718$. It grows (or decays) very fast."),
    (r'\\frac',               "↑ This fraction means: divide the top part (numerator) by the bottom part (denominator)."),
    (r'\\binom',              "↑ $\\binom{n}{k}$ reads 'n choose k' — the number of ways to pick $k$ items from $n$ items."),
    (r'\\partial',            "↑ The curly-d (∂) means 'partial derivative' — how the function changes when only ONE variable changes."),
    (r'j2\\pi|j\\omega',      "↑ $j = \\sqrt{-1}$ is the imaginary unit. $j\\omega$ represents a pure oscillation at frequency $\\omega$."),
]


def _formula_hint(latex_line: str) -> str:
    """Return a plain-English explanation for a formula, or empty string."""
    for pattern, hint in _FORMULA_HINTS:
        if re.search(pattern, latex_line):
            return hint
    return ""


# ─── Exam tips ────────────────────────────────────────────────────────────────
def _exam_tip(heading: str, body: str) -> str:
    h, b = heading.lower(), body.lower()
    if re.search(r"theorem|transform|law|series|property", h + " " + b):
        return "State the theorem/definition precisely — examiners award marks for exact wording. Include all conditions."
    if re.search(r"deriv|proof|show that|prove", b):
        return "Reproduce the derivation step-by-step — partial credit is given for each correct intermediate step."
    if re.search(r"formula|equation|expression|given by", b):
        return "Memorise the formula with all variable definitions — numerical application problems are very common."
    if re.search(r"condition|constraint|valid|converge|region|require", b):
        return "Know and state ALL conditions/constraints — often worth 1–2 dedicated marks."
    if re.search(r"application|used in|practical|real.world", b):
        return "Know at least 2–3 real-world applications — a common short-answer question."
    return "Write the formal definition first, then explain it in your own words, then give a worked example."


# ─── Beginner section builder ─────────────────────────────────────────────────
def _build_beginner_section(heading: str, body: str, all_sentences: list[str], math_lines: list[str]) -> str | None:
    """
    Build a deeply explanatory beginner section:
      1. What Is It?  (definition sentences)
      2. Why Does It Matter?  (application / importance sentences)
      3. How Does It Work?  (mechanism / procedure sentences)
      4. Real-world Analogy
      5. Any remaining key sentences
      6. Formulas — shown with plain-English annotations below each one
      7. Exam Tip
    """
    if not all_sentences:
        return None

    # Categorise sentences
    defn_s    = [s for s in all_sentences if re.search(
        r'\b(is|are|defined|means|represents|refers to|known as|called|describes)\b', s, re.I)]
    why_s     = [s for s in all_sentences if re.search(
        r'\b(used|useful|important|application|allows|enables|helps|purpose|essential|fundamental)\b', s, re.I)]
    how_s     = [s for s in all_sentences if re.search(
        r'\b(given by|calculated|computed|found by|steps|process|method|procedure|approach|first|then|finally)\b', s, re.I)]
    example_s = [s for s in all_sentences if re.search(
        r'\b(example|instance|consider|suppose|imagine|such as|for example|e\.g|think of)\b', s, re.I)]
    reason_s  = [s for s in all_sentences if re.search(
        r'\b(because|therefore|since|hence|thus|which means|this means|this is why|reason)\b', s, re.I)]

    parts = []

    # ── 1. What Is It? ────────────────────────────────────────────────────────
    what_pool = defn_s if defn_s else all_sentences[:4]
    parts.append("### 📖 What Is It?\n\n" + "\n\n".join(what_pool[:4]))

    # ── 2. Why Does It Matter? ────────────────────────────────────────────────
    if why_s or reason_s:
        why_pool = (why_s + reason_s)
        why_pool = list(dict.fromkeys(why_pool))  # dedup preserving order
        parts.append("### 🎯 Why Does It Matter?\n\n" + "\n\n".join(why_pool[:4]))

    # ── 3. How Does It Work? ──────────────────────────────────────────────────
    shown = set(what_pool[:4] + (why_s + reason_s)[:4])
    how_pool = how_s if how_s else [s for s in all_sentences if s not in shown]
    if how_pool:
        parts.append("### ⚙️ How Does It Work?\n\n" + "\n\n".join(how_pool[:4]))

    # ── 4. Concrete example ───────────────────────────────────────────────────
    if example_s:
        parts.append("### 💎 Worked Example\n\n" + "\n\n".join(example_s[:2]))

    # ── 5. Real-world analogy ─────────────────────────────────────────────────
    analogy = _get_analogy(heading, body)
    if analogy:
        parts.append(f"> {analogy}")

    # ── 6. Any remaining important sentences ──────────────────────────────────
    all_shown = set(what_pool[:4] + (why_s+reason_s)[:4] + how_pool[:4] + example_s[:2])
    leftover  = [s for s in all_sentences if s not in all_shown]
    if leftover:
        parts.append("### 📌 Also Important\n\n" + "\n\n".join(leftover[:4]))

    # ── 7. Formulas — shown with plain-English annotations ────────────────────
    if math_lines:
        formula_parts = [
            "> 💡 **Formulas for this topic** (shown for reference — don't panic, focus on the idea first!)\n"
        ]
        for ml in math_lines[:4]:
            latex = _raw_to_latex(ml)
            formula_parts.append(f"$$\n{latex}\n$$")
            hint = _formula_hint(latex)
            if hint:
                formula_parts.append(f"*{hint}*")
        parts.append("\n\n".join(formula_parts))

    if not parts:
        return None

    tip = _exam_tip(heading, body)
    return f"## {heading}\n\n" + "\n\n".join(parts) + f"\n\n> 📝 **Exam Tip:** {tip}"


# ─── Intermediate / Advanced section builder ──────────────────────────────────
def _build_standard_section(
    heading: str, body: str, top_prose: list[str], math_lines: list[str], proficiency: str
) -> str | None:
    if not top_prose:
        return None

    parts = []

    if proficiency == "Intermediate":
        defn = [s for s in top_prose if re.search(r'\b(is|are|defined|means|represents|describes)\b', s, re.I)]
        rest = [s for s in top_prose if s not in defn]
        if defn:
            parts.append("**Definition:** " + " ".join(defn[:2]))
        if rest:
            parts.append("\n\n".join(rest))
        analogy = _get_analogy(heading, body)
        if analogy:
            parts.append(f"> {analogy}")
        for ml in math_lines[:4]:
            parts.append(f"$$\n{_raw_to_latex(ml)}\n$$")

    else:  # Advanced
        parts.append("\n\n".join(top_prose))
        for ml in math_lines[:6]:
            parts.append(f"$$\n{_raw_to_latex(ml)}\n$$")

    if not parts:
        return None

    tip = _exam_tip(heading, body)
    return f"## {heading}\n\n" + "\n\n".join(parts) + f"\n\n> 📝 **Exam Tip:** {tip}"


# ─── Main section dispatcher ──────────────────────────────────────────────────
def _build_section(heading: str, body: str, prose_k: int, proficiency: str) -> str | None:
    lines      = body.split("\n")
    math_lines = []
    prose_lines = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if _is_math_line(s):
            math_lines.append(s)
        else:
            prose_lines.append(s)

    sentences = _split_sentences(" ".join(prose_lines))
    if not sentences:
        return None

    if proficiency == "Beginner":
        # Beginners get ALL sentences — no filtering, max content
        return _build_beginner_section(heading, body, sentences, math_lines)
    else:
        top_prose = _score_and_pick(sentences, prose_k) if len(sentences) > prose_k else sentences
        return _build_standard_section(heading, body, top_prose, math_lines, proficiency)


# ─── Proficiency config ───────────────────────────────────────────────────────
# KEY FIX: prose_k is now HIGHEST for Beginner — they need MORE, not less.
# Beginner notes also SHOW formulas (with plain-English annotations).
_PROF = {
    "Beginner": {
        "prose_k": 99,         # effectively "use all sentences"
        "max_sec": 20,
        "label":   "Full conceptual depth — every idea explained from scratch with analogies",
    },
    "Intermediate": {
        "prose_k": 8,
        "max_sec": 16,
        "label":   "Balanced depth — key formulas with intuition and application",
    },
    "Advanced": {
        "prose_k": 6,          # dense: fewer but heavier sentences
        "max_sec": 24,
        "label":   "Full rigour — formal definitions, derivations, edge cases",
    },
}


# ─── Public API ───────────────────────────────────────────────────────────────
def generate_local_note(slides_text: str, textbook_text: str, proficiency: str) -> str:
    """
    Generate a structured Markdown study note purely from extracted PDF text.
    No LLM required. All math symbols are converted to proper LaTeX.
    """
    cfg      = _PROF.get(proficiency, _PROF["Intermediate"])
    prose_k  = cfg["prose_k"]
    max_sec  = cfg["max_sec"]

    slides_text   = _clean_pdf_text(slides_text)
    textbook_text = _clean_pdf_text(textbook_text)

    sections: list[str] = []
    seen:     set[str]  = set()

    def add_sections(text: str, suffix: str = ""):
        for heading, body in _split_sections(text):
            if len(sections) >= max_sec:
                break
            key = re.sub(r"\s+", " ", heading.lower().strip())
            if key in seen:
                continue
            seen.add(key)
            sec = _build_section(heading + suffix, body, prose_k, proficiency)
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

    level_banner = {
        "Beginner":     "🔰 **Beginner mode** — Every concept is taught from scratch. Read each section fully, follow the analogies before looking at formulas.",
        "Intermediate": "⚡ **Intermediate mode** — Key definitions, formulas, and worked intuition.",
        "Advanced":     "🎯 **Advanced mode** — Full rigour: derivations, edge cases, formal notation.",
    }.get(proficiency, "")

    header = (
        f"# AuraGraph Study Notes\n\n"
        f"**Proficiency: {proficiency}** — {cfg['label']}\n\n"
        f"> {level_banner}\n\n"
        f"> ⚠️ **Offline mode:** notes generated without AI. "
        f"Add Azure OpenAI keys to `backend/.env` for true AI-fused notes.\n"
    )
    return header + "\n\n---\n\n" + "\n\n---\n\n".join(sections)
"""
agents/local_summarizer.py  — AuraGraph offline fallback
Generates clean structured study notes from PDF text WITHOUT using any LLM API.

Design philosophy:
  - Produce READABLE, CLEAN markdown — never mangle math symbols
  - Preserve any formula lines as-is (wrapped in block LaTeX $$...$$)
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
def _build_section(heading: str, body: str, prose_k: int, include_math: bool, is_beginner: bool) -> str | None:
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

    # Beginner gets simplified language + intuition block directly injected
    if is_beginner:
        parts.append(f"🔰 **Core Concept:** {top_prose[0]}" if top_prose else "")
        if len(top_prose) > 1:
            parts.append("💡 **Intuition:** " + top_prose[1])
        if len(top_prose) > 2:
            parts.append("\n\n".join(top_prose[2:]))
    else:
        parts.append("\n\n".join(top_prose))

    # Math / formulae (wrapped in KaTeX display math block $$...$$)
    if include_math and math_lines:
        for mline in math_lines[:4]:  # cap at 4 formula lines
            parts.append(f"$$\n{mline}\n$$")

    if not parts:
        return None

    tip = _exam_tip(heading, body)
    section_body = "\n\n".join(parts)
    return f"## {heading}\n\n{section_body}\n\n> 📝 **Exam Tip:** {tip}"


# ─── Proficiency config ───────────────────────────────────────────────────────
_PROF = {
    "Beginner":     {"prose_k": 4, "include_math": False, "max_sec": 12, "is_beginner": True,
                     "label": "Conceptual focus — core ideas, zero math"},
    "Intermediate": {"prose_k": 6, "include_math": True,  "max_sec": 16, "is_beginner": False,
                     "label": "Balanced depth — key formulas with explanation"},
    "Advanced":     {"prose_k": 8, "include_math": True,  "max_sec": 24, "is_beginner": False,
                     "label": "Full depth — derivations, formulas, edge-case conditions"},
}


# ─── Public API ───────────────────────────────────────────────────────────────
def generate_local_note(slides_text: str, textbook_text: str, proficiency: str) -> str:
    """
    Generate a structured Markdown study note purely from extracted PDF text.
    No LLM, no regex math conversion — just clean extractive summarization.
    """
    cfg = _PROF.get(proficiency, _PROF["Intermediate"])
    prose_k     = cfg["prose_k"]
    incl_math   = cfg["include_math"]
    max_sec     = cfg["max_sec"]
    is_beginner = cfg["is_beginner"]

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
            sec = _build_section(heading + label_suffix, body, prose_k, incl_math, is_beginner)
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
        f"> ⚠️ **Note:** These notes are generated using the `local_summarizer` fallback engine. "
        f"Add your Azure OpenAI keys to `backend/.env` for true AI-fused notes.\n"
    )
    return header + "\n\n---\n\n" + "\n\n---\n\n".join(sections)
