"""
Local (offline) Mutation — AuraGraph fallback
Rewrites a paragraph when Azure OpenAI is unavailable.

Strategy:
  1. Parse what the student is confused about from their doubt
  2. Add an explicit note addressing the doubt directly to the paragraph
  3. Highlight the key concept and add a plain-language clarification block
  4. Return a structured mutation result
"""
import re
import json


# ── Concept-gap heuristics ────────────────────────────────────────────────────
_CONFUSION_KEYWORDS = {
    "why": "The student is unclear about the reasoning or motivation behind this concept.",
    "what": "The student needs a clearer definition of the concept.",
    "how": "The student needs a step-by-step explanation of the mechanism.",
    "don't understand": "There is a fundamental conceptual gap requiring a re-explanation.",
    "confused": "The explanation lacks sufficient clarity or an intuitive analogy.",
    "difference": "The student cannot distinguish between two related concepts.",
    "when": "The student is uncertain about the conditions for applying this concept.",
    "prove": "The student requires a derivation or proof of the stated result.",
    "example": "An illustrative worked example would resolve the confusion.",
    "intuitively": "The student needs an intuitive (non-mathematical) explanation.",
}


def _diagnose_gap(doubt: str) -> str:
    doubt_lower = doubt.lower()
    for keyword, diagnosis in _CONFUSION_KEYWORDS.items():
        if keyword in doubt_lower:
            return diagnosis
    return "The student requires additional context and an intuitive explanation of this concept."


# ── Simple paragraph rewriter ─────────────────────────────────────────────────
def _build_analogy_hint(doubt: str) -> str:
    """Return a short analogy/clarification sentence based on the doubt."""
    dl = doubt.lower()
    if "convolution" in dl or "conv" in dl:
        return ("Think of it as sliding a 'weighing window' across a signal: "
                "at each position you compute a weighted sum of overlapping values.")
    if "fourier" in dl or "frequency" in dl or "spectrum" in dl:
        return ("The Fourier Transform decomposes a signal into its constituent frequencies, "
                "much like a musical chord being split into individual notes.")
    if "laplace" in dl:
        return ("The Laplace Transform generalises the Fourier Transform by adding a "
                "decay factor, allowing analysis of signals that do not naturally converge.")
    if "z-transform" in dl or "z transform" in dl:
        return ("The Z-Transform is the discrete-time counterpart of the Laplace Transform — "
                "replacing continuous exponentials with powers of a complex variable z.")
    if "differential" in dl or "derivative" in dl:
        return ("Think of a derivative as measuring the instantaneous slope — "
                "how quickly the quantity is changing at a single point.")
    if "integral" in dl or "integration" in dl:
        return ("Integration accumulates the area under a curve, "
                "aggregating infinitely many infinitely thin slices into a total sum.")
    if "matrix" in dl or "eigen" in dl:
        return ("An eigenvector is a special direction that a transformation only stretches "
                "or shrinks, never rotates — its scaling factor is the eigenvalue.")
    # Generic fallback
    return ("To build intuition: try to identify a real-world analogy "
            "or work through the smallest possible concrete example first.")


def local_mutate(original_paragraph: str, student_doubt: str) -> tuple[str, str]:
    """
    Returns (mutated_paragraph, concept_gap_diagnosis).
    Works entirely offline without any API calls.
    """
    concept_gap = _diagnose_gap(student_doubt)
    analogy = _build_analogy_hint(student_doubt)

    # Trim long paragraphs for readability
    body = original_paragraph.strip()

    # Build the mutated paragraph
    # 1. Keep original content
    # 2. Append a "Clarification" block addressing the doubt
    clarification = (
        f"\n\n**Clarification (in response to: _{student_doubt.strip()}_):** "
        f"{analogy} "
        f"Remember that {concept_gap.lower()} "
        f"If this section still feels unclear, try working through a minimal numeric example "
        f"before re-reading the formal statement above."
    )

    mutated = body + clarification
    return mutated, concept_gap
