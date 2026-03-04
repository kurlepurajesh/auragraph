"""
Local Concept Extractor — AuraGraph
Extracts concept nodes and dependency edges from a fused Markdown note.

Used to auto-populate the per-notebook Cognitive Knowledge Graph without
needing Azure Cosmos DB Graph API.
"""
import re
from typing import Any


# ── Concept keywords to detect ────────────────────────────────────────────────
# Each entry: (regex_pattern, canonical_label, default_x%, default_y%)
_CONCEPT_PATTERNS: list[tuple[str, str, int, int]] = [
    # Signals & Systems
    (r'\bfourier\s*transform\b',        "Fourier Transform",    50, 10),
    (r'\binverse\s*fourier\b',          "Inverse Fourier",      75, 10),
    (r'\bconvolution\s*theorem\b',      "Convolution Theorem",  50, 30),
    (r'\bconvolution\b',                "Convolution",          35, 30),
    (r'\blti\s*system\b|linear\s*time.invariant', "LTI Systems", 20, 55),
    (r'\bfrequency\s*response\b',       "Frequency Response",   80, 55),
    (r'\bimpulse\s*response\b',         "Impulse Response",     20, 40),
    (r'\btransfer\s*function\b',        "Transfer Function",    80, 40),
    (r'\bz.transform\b',                "Z-Transform",          50, 75),
    (r'\bdtft\b|discrete.time\s*fourier', "DTFT",              65, 55),
    (r'\bdft\b|discrete\s*fourier\b',   "DFT / FFT",           65, 70),
    (r'\blaplace\s*transform\b',        "Laplace Transform",   35, 75),
    (r'\bsampling\s*theorem\b|nyquist', "Sampling Theorem",    50, 90),
    (r'\bparseval',                     "Parseval's Theorem",  80, 75),
    # Mathematics
    (r'\beigenvalue\b|\beigenvector\b', "Eigenvalues",         40, 20),
    (r'\bmatrix\s*multiplication\b',    "Matrix Operations",   60, 20),
    (r'\bdifferential\s*equation',      "Differential Eqns",   25, 65),
    (r'\btaylor\s*series\b',            "Taylor Series",       70, 25),
    (r'\blimit\b.*calculus|calculus.*\blimit\b', "Limits",     30, 10),
    (r'\bderivative\b|\bdifferentiation\b', "Derivatives",    45, 40),
    (r'\bintegral\b|\bintegration\b',   "Integration",         55, 40),
    # CS / Algorithms
    (r'\bbig.?o\s*notation\b|\btime\s*complexity\b', "Time Complexity", 50, 20),
    (r'\bbinary\s*search\b',            "Binary Search",       30, 40),
    (r'\bdynamic\s*programming\b',      "Dynamic Programming", 70, 40),
    (r'\bgraph\s*traversal\b|bfs|dfs',  "Graph Traversal",     50, 60),
    (r'\bsorting\s*algorithm\b',        "Sorting Algorithms",  50, 80),
    # Machine Learning
    (r'\bneural\s*network\b',           "Neural Networks",     50, 20),
    (r'\bgradient\s*descent\b',         "Gradient Descent",    30, 40),
    (r'\bbackpropagation\b',            "Backpropagation",     70, 40),
    (r'\boverfitting\b|\bunderfitting\b', "Overfitting",       50, 60),
    (r'\bregularization\b|\bregularisation\b', "Regularization", 50, 75),
    # Physics
    (r'\bnewton.s\s*law',               "Newton's Laws",       50, 20),
    (r'\bthermodynamics\b',             "Thermodynamics",      30, 50),
    (r'\belectromagnet',                "Electromagnetism",    70, 50),
    (r'\bquantum\s*mechanic',           "Quantum Mechanics",   50, 80),
]

# ── Dependency edges ──────────────────────────────────────────────────────────
# (label_a, label_b) → edge implies a is prerequisite for b
_DEPENDENCIES: list[tuple[str, str]] = [
    ("Fourier Transform", "Convolution Theorem"),
    ("Fourier Transform", "DTFT"),
    ("Fourier Transform", "Inverse Fourier"),
    ("Convolution Theorem", "LTI Systems"),
    ("Convolution Theorem", "Frequency Response"),
    ("Impulse Response", "LTI Systems"),
    ("LTI Systems", "Z-Transform"),
    ("Transfer Function", "Z-Transform"),
    ("DTFT", "DFT / FFT"),
    ("Z-Transform", "Sampling Theorem"),
    ("Frequency Response", "Sampling Theorem"),
    ("Fourier Transform", "Parseval's Theorem"),
    ("Derivatives", "Differential Eqns"),
    ("Integration", "Differential Eqns"),
    ("Limits", "Derivatives"),
    ("Limits", "Integration"),
    ("Eigenvalues", "Matrix Operations"),
    ("Neural Networks", "Gradient Descent"),
    ("Gradient Descent", "Backpropagation"),
    ("Backpropagation", "Overfitting"),
    ("Overfitting", "Regularization"),
]


def extract_concepts(note_text: str) -> dict[str, Any]:
    """
    Scan a Markdown note and return a graph dict:
    { "nodes": [...], "edges": [...] }

    Nodes are assigned:
    - status "partial" by default (not yet mastered)
    - Positions spread across the canvas
    """
    text_lower = note_text.lower()
    found: list[dict] = []
    seen_labels: set[str] = set()

    node_id = 1
    for pattern, label, x, y in _CONCEPT_PATTERNS:
        if label in seen_labels:
            continue
        if re.search(pattern, text_lower):
            found.append({
                "id": node_id,
                "label": label,
                "status": "partial",
                "x": x,
                "y": y,
            })
            seen_labels.add(label)
            node_id += 1

    # Build edges from found concepts
    edges: list[list[int]] = []
    label_to_id = {n["label"]: n["id"] for n in found}
    for src_label, dst_label in _DEPENDENCIES:
        if src_label in label_to_id and dst_label in label_to_id:
            edges.append([label_to_id[src_label], label_to_id[dst_label]])

    # If nothing matched, return a minimal placeholder graph
    if not found:
        found = [
            {"id": 1, "label": "Core Concept", "status": "partial", "x": 50, "y": 50}
        ]
        edges = []

    return {"nodes": found, "edges": edges}
