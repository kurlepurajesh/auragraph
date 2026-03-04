import re

_CONFUSION_KEYWORDS = {
    "why": "The student is unclear about the reasoning behind this concept.",
    "what": "The student needs a clearer definition.",
    "how": "The student needs a step-by-step explanation.",
    "don't understand": "There is a fundamental conceptual gap.",
    "confused": "The explanation lacks sufficient clarity.",
    "difference": "The student cannot distinguish between two related concepts.",
    "example": "An illustrative worked example would resolve the confusion.",
    "intuition": "The student needs an intuitive explanation.",
}


def _diagnose_gap(doubt):
    doubt_lower = doubt.lower()
    topic_keywords = {
        "convolution": "The student needs an intuitive explanation of what convolution computes.",
        "fourier": "The student needs to understand frequency decomposition conceptually.",
        "laplace": "The student needs to understand why/how Laplace generalises Fourier.",
        "binomial": "The student cannot distinguish between Binomial's parameters and meaning.",
        "poisson": "The student doesn't know when to apply Poisson vs Binomial.",
        "eigenvalue": "The student needs a geometric intuition for eigenvalues.",
        "derivative": "The student needs the instantaneous-rate-of-change intuition.",
    }
    for keyword, diagnosis in topic_keywords.items():
        if keyword in doubt_lower:
            return diagnosis
    for keyword, diagnosis in _CONFUSION_KEYWORDS.items():
        if keyword in doubt_lower:
            return diagnosis
    return "The student requires additional context and an intuitive explanation."


def _build_analogy_hint(doubt):
    dl = doubt.lower()
    if "convolution" in dl:
        return "Think of it as sliding a weighing window across a signal."
    if "fourier" in dl:
        return "The Fourier Transform decomposes a signal into its constituent frequencies."
    if "laplace" in dl:
        return "The Laplace Transform generalises the Fourier Transform by adding a decay factor."
    if "derivative" in dl:
        return "Think of a derivative as measuring the instantaneous slope."
    if "integral" in dl:
        return "Integration accumulates the area under a curve."
    return "Try to identify a real-world analogy or work through the smallest possible concrete example."


def local_mutate(original_paragraph, student_doubt):
    concept_gap = _diagnose_gap(student_doubt)
    analogy = _build_analogy_hint(student_doubt)
    body = original_paragraph.strip()
    lines = body.split("\n")
    heading = ""
    rest = body
    for i, line in enumerate(lines):
        if line.startswith("## ") or line.startswith("# "):
            heading = line
            rest = "\n".join(lines[i + 1:]).strip()
            break
    insight_block = f"> **Intuition (re: \"{student_doubt.strip()}\"):** {analogy} _{concept_gap}_"
    if heading:
        mutated = f"{heading}\n\n{insight_block}\n\n{rest}"
    else:
        mutated = f"{insight_block}\n\n{rest}"
    return mutated, concept_gap
