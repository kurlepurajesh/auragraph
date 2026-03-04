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
    "formula": "The student doesn't understand the formula or what its symbols mean.",
    "meaning": "The student needs a definition in plain language.",
    "when": "The student doesn't know when to apply this concept.",
}


def _diagnose_gap(doubt):
    doubt_lower = doubt.lower()
    topic_keywords = {
        "convolution": "The student needs an intuitive explanation of what convolution computes - sliding a window of weights across a signal.",
        "fourier": "The student needs to understand frequency decomposition - any signal is a sum of sine waves.",
        "laplace": "The student needs to understand why Laplace generalises Fourier by adding a real decay factor.",
        "binomial": "The student cannot distinguish between the Binomial parameters n (trials) and p (probability per trial).",
        "poisson": "The student doesn't know when to apply Poisson (rare events with known rate) vs Binomial (fixed trials).",
        "eigenvalue": "The student needs a geometric intuition - eigenvectors are directions that only get scaled, not rotated.",
        "derivative": "The student needs the instantaneous-rate-of-change intuition - slope of the tangent line at a point.",
        "hypergeometric": "The student needs to understand sampling without replacement - items are not put back after drawing.",
        "variance": "The student needs to understand variance as the average squared distance from the mean.",
        "expectation": "The student needs to understand expected value as the long-run average if you repeated the experiment many times.",
    }
    for keyword, diagnosis in topic_keywords.items():
        if keyword in doubt_lower:
            return diagnosis
    for keyword, diagnosis in _CONFUSION_KEYWORDS.items():
        if keyword in doubt_lower:
            return diagnosis
    return "The student requires additional context, a simpler explanation, and a concrete example."


def _build_intuition(doubt):
    dl = doubt.lower()
    if "convolution" in dl:
        return "Think of convolution as sliding a weighing window across a signal. At each position, you multiply the overlapping parts and add them up. It's like smoothing a bumpy road with a weighted roller."
    if "fourier" in dl:
        return "The Fourier Transform decomposes any signal into its constituent frequencies - like how a prism splits white light into a rainbow of colors. Each frequency component has an amplitude and phase."
    if "laplace" in dl:
        return "The Laplace Transform is like the Fourier Transform but with an extra 'decay factor'. This lets it handle signals that grow over time, making it more powerful for analyzing systems."
    if "derivative" in dl:
        return "A derivative measures how fast something is changing at a specific instant. If you're driving and your speedometer reads 60 km/h, that's the derivative of your position with respect to time."
    if "integral" in dl:
        return "Integration accumulates the area under a curve. Think of it as adding up infinitely many thin vertical strips to find the total area."
    if "hypergeometric" in dl:
        return "Imagine a bag with red and blue marbles. You draw some out WITHOUT putting them back. The hypergeometric distribution tells you the probability of getting a certain number of red marbles."
    if "binomial" in dl:
        return "The binomial distribution counts successes in repeated independent trials - like flipping a coin n times and counting heads. Each flip is independent and has the same probability."
    if "variance" in dl:
        return "Variance measures how spread out values are from the average. Low variance means values cluster near the mean; high variance means they're scattered far apart."
    if "formula" in dl or "symbol" in dl or "equation" in dl:
        return "Let's break down the formula symbol by symbol so every part makes sense."
    return "Let's re-approach this concept from scratch with a concrete, everyday analogy."


def local_mutate(original_paragraph, student_doubt):
    concept_gap = _diagnose_gap(student_doubt)
    intuition = _build_intuition(student_doubt)

    body = original_paragraph.strip()
    lines = body.split("\n")

    # Extract heading if present
    heading = ""
    rest_lines = []
    found_heading = False
    for line in lines:
        if not found_heading and (line.startswith("## ") or line.startswith("# ")):
            heading = line
            found_heading = True
        else:
            rest_lines.append(line)
    rest = "\n".join(rest_lines).strip()

    # Build the mutated section
    parts = []
    if heading:
        parts.append(heading)
    parts.append("")
    parts.append(f"> **Intuition (addressing your doubt):** {intuition}")
    parts.append("")
    parts.append(f"*Your confusion: \"{student_doubt.strip()}\"*")
    parts.append("")
    parts.append(f"**What's happening here:** {concept_gap}")
    parts.append("")
    if rest:
        parts.append(rest)
    parts.append("")
    parts.append(f"> **Exam Tip:** When you see this concept in an exam, start by recalling the intuition above. Write the definition first, then apply the formula step by step.")

    mutated = "\n".join(parts)
    return mutated, concept_gap
