"""
Local Concept Extractor — AuraGraph
Extracts concept nodes and dependency edges from a fused Markdown note.

Used to auto-populate the per-notebook Cognitive Knowledge Graph without
needing Azure Cosmos DB Graph API.
"""
import json
import os
import re
import time
from typing import Any


# ── Generic concept keyword → node patterns ─────────────────────────────
# Format: (regex, canonical_label, default_x%, default_y%)
_CONCEPT_PATTERNS: list[tuple[str, str, int, int]] = [
    # ── Signals & Systems ────────────────────────────────────────────────────────
    (r'\bfourier\s*transform\b',           'Fourier Transform',    50, 10),
    (r'\binverse\s*fourier\b',             'Inverse Fourier',      75, 10),
    (r'\bconvolution\s*theorem\b',         'Convolution Theorem',  50, 30),
    (r'\bconvolution\b',                   'Convolution',          35, 30),
    (r'\blti\s*system|linear\s*time.invariant', 'LTI Systems',     20, 55),
    (r'\bfrequency\s*response\b',          'Frequency Response',   80, 55),
    (r'\bimpulse\s*response\b',            'Impulse Response',     20, 40),
    (r'\btransfer\s*function\b',           'Transfer Function',    80, 40),
    (r'\bz.transform\b',                   'Z-Transform',          50, 75),
    (r'\bdtft\b|discrete.time\s*fourier',  'DTFT',                 65, 55),
    (r'\bdft\b|discrete\s*fourier\b',      'DFT / FFT',            65, 70),
    (r'\blaplace\s*transform\b',           'Laplace Transform',    35, 75),
    (r'\bsampling\s*theorem|nyquist',      'Sampling Theorem',     50, 90),
    (r'\bparseval',                        "Parseval's Theorem",   80, 75),
    # ── Probability & Statistics ───────────────────────────────────────────────
    (r'\brandom\s*variable',               'Random Variables',     40, 10),
    (r'\bprobability\s*distribution',      'Probability Dist.',    60, 10),
    (r'\bexpected\s*value|\bE\[',          'Expected Value',       40, 25),
    (r'\bvariance\b|\bVar\(',              'Variance',             60, 25),
    (r'\bstandard\s*deviation',            'Std Deviation',        80, 20),
    (r'\bbayes\s*theorem|\bbayes.\s*rule', "Bayes' Theorem",       50, 40),
    (r'\bconditional\s*probability',       'Conditional Prob.',    30, 40),
    (r'\bindependen',                      'Independence',         70, 40),
    (r'\bnormal\s*distribution|\bgaussian', 'Normal Distribution', 50, 55),
    (r'\bbernoulli\s*dist|\bbernoulli\s*random|\bbernoulli\s*trial', 'Bernoulli Distribution', 15, 55),
    (r'\bbinomial\s*distribution',         'Binomial Dist.',       25, 55),
    (r'\bpoisson\s*distribution',          'Poisson Dist.',        75, 55),
    (r'\buniform\s*distribution',          'Uniform Distribution', 85, 45),
    (r'\bgeometric\s*distribution',        'Geometric Dist.',      15, 70),
    (r'\bnegative\s*binomial',             'Negative Binomial',    25, 70),
    (r'\bexponential\s*distribution',      'Exponential Dist.',    75, 70),
    (r'\bgamma\s*distribution',            'Gamma Distribution',   85, 70),
    (r'\bcentral\s*limit\s*theorem',       'Central Limit Theorem',50, 70),
    (r'\bmoment\s*generat|\bMGF\b',        'MGF',                  35, 70),
    (r'\bcumulative\s*dist|\bCDF\b',       'CDF',                  65, 70),
    (r'\bpdf\b|probability\s*density',     'PDF',                  50, 85),
    (r'\bhypothesis\s*test',               'Hypothesis Testing',   30, 85),
    (r'\bconfidence\s*interval',           'Confidence Interval',  70, 85),
    (r'\bmarkov\s*chain',                  'Markov Chains',        50, 95),
    # ── Linear Algebra ──────────────────────────────────────────────────────────────
    (r'\beigenvalue|\beigenvector',         'Eigenvalues / Vectors',40, 20),
    (r'\bmatrix\s*multiplication|\bmatrix\s*product', 'Matrix Operations', 60, 20),
    (r'\blinear\s*(in)?dependen',          'Linear Independence',  20, 35),
    (r'\bspan\b.*vector|\bvector\s*space', 'Vector Spaces',        80, 35),
    (r'\borthogon',                        'Orthogonality',        50, 50),
    (r'\bsingular\s*value|\bSVD\b',        'SVD',                  50, 65),
    (r'\bdeterminant\b',                   'Determinant',          30, 65),
    (r'\binverse\s*matrix',                'Matrix Inverse',       70, 65),
    # ── Calculus & Analysis ──────────────────────────────────────────────────────────
    (r'\bdifferential\s*equation',         'Differential Eqns',   25, 65),
    (r'\btaylor\s*series',                 'Taylor Series',        70, 25),
    (r'\blimit\b.{0,20}calculus|calculus.{0,20}\blimit', 'Limits', 30, 10),
    (r'\bderivative|\bdifferentiation',    'Derivatives',          45, 40),
    (r'\bintegral|\bintegration',          'Integration',          55, 40),
    (r'\bgradient\b',                      'Gradient',             50, 30),
    (r'\bpartial\s*derivative',            'Partial Derivatives',  70, 40),
    # ── Machine Learning ──────────────────────────────────────────────────────────────
    (r'\bneural\s*network',                'Neural Networks',      50, 10),
    (r'\bgradient\s*descent',              'Gradient Descent',     30, 25),
    (r'\bbackpropagation',                 'Backpropagation',      70, 25),
    (r'\boverfitting|\bunderfitting',       'Overfitting',          50, 40),
    (r'\bregularization|\bregularisation', 'Regularization',       50, 55),
    (r'\bsupport\s*vector|\bSVM\b',        'SVM',                  20, 40),
    (r'\bdecision\s*tree',                 'Decision Trees',       80, 40),
    (r'\brandom\s*forest',                 'Random Forest',        80, 55),
    (r'\bk.means|\bclustering',            'Clustering',           20, 55),
    (r'\bprincipal\s*component|\bPCA\b',   'PCA',                  50, 70),
    (r'\bconvolutional\s*neural|\bCNN\b',  'CNN',                  30, 70),
    (r'\brecurrent\s*neural|\bRNN\b|\bLSTM\b', 'RNN / LSTM',      70, 70),
    (r'\battention\s*mechanism|\btransformer\b', 'Transformers',   50, 85),
    (r'\bloss\s*function',                 'Loss Functions',       35, 85),
    (r'\bactivation\s*function',           'Activation Functions', 65, 85),
    # ── Algorithms & Data Structures ──────────────────────────────────────────────
    (r'\bbig.?o\s*notation|\btime\s*complexity', 'Time Complexity', 50, 20),
    (r'\bbinary\s*search',                 'Binary Search',        30, 40),
    (r'\bdynamic\s*programming',           'Dynamic Programming',  70, 40),
    (r'\bgraph\s*traversal|\bbfs\b|\bdfs\b', 'Graph Traversal',   50, 60),
    (r'\bsorting\s*algorithm',             'Sorting Algorithms',   50, 75),
    (r'\bhash\s*table|\bhashing',          'Hash Tables',          20, 60),
    (r'\btree\s*data\s*structure|\bbinary\s*tree', 'Trees',        80, 60),
    (r'\bheap\s*data\s*structure',         'Heaps',                35, 75),
    (r'\bgraph\s*algo|\bshortest\s*path|\bdijkstra', "Dijkstra's Algo", 65, 75),
    (r'\bgreedy\s*algorithm',              'Greedy Algorithms',    50, 90),
    # ── Databases ──────────────────────────────────────────────────────────────────
    (r'\bSQL\b|\brelational\s*database',   'SQL / Relational DB',  40, 20),
    (r'\bjoin\b.{0,20}\btable|\binner\s*join|\bouter\s*join', 'SQL Joins', 60, 20),
    (r'\bnormalization\b|\bNF\b',          'Normalization',        40, 40),
    (r'\btransaction\b|\bACID\b',          'Transactions / ACID',  60, 40),
    (r'\bindex\b.{0,20}database|\bB.tree\b', 'Indexing',          50, 60),
    # ── Operating Systems ───────────────────────────────────────────────────────────
    (r'\bprocess\s*scheduling|\bcpu\s*scheduling', 'CPU Scheduling', 40, 25),
    (r'\bdeadlock\b',                      'Deadlock',             60, 25),
    (r'\bvirtual\s*memory|\bpaging',       'Virtual Memory',       40, 50),
    (r'\bsemaphore|\bmutex|\bsynchronization', 'Synchronization',  60, 50),
    # ── Networking ───────────────────────────────────────────────────────────────
    (r'\bTCP.IP\b|\bTCP\b|\bUDP\b',        'TCP / UDP',            30, 30),
    (r'\bHTTP\b|\bHTTPS\b',                'HTTP / HTTPS',         70, 30),
    (r'\bOSI\s*model|\bnetwork\s*layer',   'OSI Model',            50, 50),
    (r'\bDNS\b|\bdomain\s*name',           'DNS',                  50, 70),
    # ── Physics ───────────────────────────────────────────────────────────────────
    (r"\bnewton.s\s*law",                  "Newton's Laws",        50, 20),
    (r'\bthermodynamics\b',                'Thermodynamics',       30, 50),
    (r'\belectromagnet',                   'Electromagnetism',     70, 50),
    (r'\bquantum\s*mechanic',              'Quantum Mechanics',    50, 80),
    (r'\bfluid\s*mechanic|\bbernoulli',    'Fluid Mechanics',      30, 70),
    # ── Economics / Finance ───────────────────────────────────────────────────────────
    (r'\bsupply\s*and\s*demand|\bmarket\s*equilibrium', 'Supply & Demand', 40, 25),
    (r'\belasticity\b',                    'Elasticity',           60, 25),
    (r'\bnet\s*present\s*value|\bNPV|\bDCF', 'NPV / DCF',         40, 50),
    (r'\bmonopoly|\boligopoly',            'Market Structures',    60, 50),
]

# ── Dependency edges ────────────────────────────────────────────────────────────────────────────
# (label_a, label_b) → edge implies a is prerequisite for b
_DEPENDENCIES: list[tuple[str, str]] = [
    # Signals
    ('Fourier Transform', 'Convolution Theorem'),
    ('Fourier Transform', 'DTFT'),
    ('Fourier Transform', 'Inverse Fourier'),
    ('Convolution Theorem', 'LTI Systems'),
    ('Convolution Theorem', 'Frequency Response'),
    ('Impulse Response', 'LTI Systems'),
    ('LTI Systems', 'Z-Transform'),
    ('Transfer Function', 'Z-Transform'),
    ('DTFT', 'DFT / FFT'),
    ('Z-Transform', 'Sampling Theorem'),
    ('Frequency Response', 'Sampling Theorem'),
    ('Fourier Transform', "Parseval's Theorem"),
    # Calculus
    ('Derivatives', 'Differential Eqns'),
    ('Integration', 'Differential Eqns'),
    ('Limits', 'Derivatives'),
    ('Limits', 'Integration'),
    ('Derivatives', 'Partial Derivatives'),
    ('Partial Derivatives', 'Gradient'),
    # Linear Algebra
    ('Eigenvalues / Vectors', 'Matrix Operations'),
    ('Matrix Operations', 'SVD'),
    ('Linear Independence', 'Vector Spaces'),
    # Probability & Stats
    ('Random Variables', 'Expected Value'),
    ('Random Variables', 'Variance'),
    ('Expected Value', 'Variance'),
    ('Variance', 'Std Deviation'),
    ('Conditional Prob.', "Bayes' Theorem"),
    ('Probability Dist.', 'Normal Distribution'),
    ('Probability Dist.', 'Binomial Dist.'),
    ('Probability Dist.', 'Poisson Dist.'),
    ('Random Variables', 'MGF'),
    ('Random Variables', 'CDF'),
    ('CDF', 'PDF'),
    ('Normal Distribution', 'Central Limit Theorem'),
    # ML
    ('Neural Networks', 'Gradient Descent'),
    ('Gradient Descent', 'Backpropagation'),
    ('Backpropagation', 'Overfitting'),
    ('Overfitting', 'Regularization'),
    ('Gradient', 'Gradient Descent'),
    ('Loss Functions', 'Gradient Descent'),
    ('Activation Functions', 'Neural Networks'),
    ('Neural Networks', 'CNN'),
    ('Neural Networks', 'RNN / LSTM'),
    ('RNN / LSTM', 'Transformers'),
    ('PCA', 'Clustering'),
    # Algorithms
    ('Time Complexity', 'Binary Search'),
    ('Time Complexity', 'Sorting Algorithms'),
    ('Binary Search', 'Dynamic Programming'),
    ('Trees', 'Heaps'),
    ("Dijkstra's Algo", 'Graph Traversal'),
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

    # If nothing matched, try extracting headings from the note as generic concept nodes
    if not found:
        headings = re.findall(r'^#{1,3}\s+(.+)$', note_text, re.MULTILINE)
        # Filter out the main title (first heading) and noise
        candidates = [
            h.strip() for h in headings
            if 5 < len(h.strip()) < 50
            and not re.search(r'aura\s*graph|study\s*notes|proficiency', h, re.I)
        ]
        # Layout in a grid
        for i, label in enumerate(candidates[:12]):
            col = i % 3
            row = i // 3
            found.append({
                'id': i + 1,
                'label': label[:30],
                'status': 'partial',
                'x': 20 + col * 30,
                'y': 15 + row * 25,
            })
        if found:
            # Chain them sequentially if we have multiple
            edges = [[i, i + 1] for i in range(1, len(found))]
        else:
            # Absolute last resort
            found = [{'id': 1, 'label': 'Core Concept', 'status': 'partial', 'x': 50, 'y': 50}]
            edges = []

    return {'nodes': found, 'edges': edges}


# ─── LLM-powered extractor (works for any subject) ──────────────────────────
_LLM_EXTRACT_PROMPT = """You are a concept-graph extractor for a study-notes platform.
Given the following study notes, identify {n_nodes} key concepts and their dependency/prerequisite relationships.

Return ONLY a valid JSON object. No markdown fences, no prose.
Exact schema required:
{{
  "nodes": [
    {{"id": 1, "label": "Concept Name", "x": 50, "y": 10}},
    ...
  ],
  "edges": [[src_id, dst_id], ...]
}}

Rules:
- Labels must be ≤ 30 characters and SPECIFIC — include the full name, e.g.
  "Bernoulli Distribution" (NOT just "Bernoulli"), "Poisson Distribution" (NOT "Poisson"),
  "Normal Distribution", "Bayes Theorem", "Central Limit Theorem" etc.
- For probability distributions always append " Distribution" or " Dist." to the name.
- x and y are integers from 5 to 95 representing canvas position (%).
- Spread nodes evenly — avoid clustering everything at the same spot.
- Edges flow from prerequisite → dependent concept.
- Every node id must be unique starting from 1.

NOTES:
{note_text}
"""


async def llm_extract_concepts(note_text: str) -> dict:
    """LLM-powered concept extractor — works for any subject, not just STEM.
    Requires GROQ_API_KEY env var; falls back to regex extract_concepts() on any failure."""
    import httpx  # lazy import — not needed for the sync path

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return extract_concepts(note_text)

    # Truncate to avoid token overflow; keep the most informative beginning
    snippet = note_text[:6000]
    n_nodes = 10 if len(note_text) < 2000 else 14
    prompt  = _LLM_EXTRACT_PROMPT.format(note_text=snippet, n_nodes=n_nodes)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.2,
                },
            )
        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if the model wrapped the JSON anyway
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

        graph = json.loads(raw)
        if not isinstance(graph.get("nodes"), list) or not graph["nodes"]:
            raise ValueError("Empty nodes array")

        # Normalise: ensure required fields exist
        for n in graph["nodes"]:
            n.setdefault("status", "partial")
            n.setdefault("x", 50)
            n.setdefault("y", 50)
            n.setdefault("mutation_count", 0)
            n["label"] = str(n.get("label", "Concept"))[:30]
        if not isinstance(graph.get("edges"), list):
            graph["edges"] = []

        return graph

    except Exception:
        return extract_concepts(note_text)
