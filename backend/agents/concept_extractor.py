import re


_CONCEPT_PATTERNS = [
    (r'\bfourier\s*transform\b', 'Fourier Transform', 50, 10),
    (r'\binverse\s*fourier\b', 'Inverse Fourier', 75, 10),
    (r'\bconvolution\s*theorem\b', 'Convolution Theorem', 50, 30),
    (r'\bconvolution\b', 'Convolution', 35, 30),
    (r'\blti\s*system|linear\s*time.invariant', 'LTI Systems', 20, 55),
    (r'\bfrequency\s*response\b', 'Frequency Response', 80, 55),
    (r'\bimpulse\s*response\b', 'Impulse Response', 20, 40),
    (r'\btransfer\s*function\b', 'Transfer Function', 80, 40),
    (r'\bz.transform\b', 'Z-Transform', 50, 75),
    (r'\bdtft\b|discrete.time\s*fourier', 'DTFT', 65, 55),
    (r'\bdft\b|discrete\s*fourier\b', 'DFT / FFT', 65, 70),
    (r'\blaplace\s*transform\b', 'Laplace Transform', 35, 75),
    (r'\bsampling\s*theorem|nyquist', 'Sampling Theorem', 50, 90),
    (r'\bparseval', "Parseval's Theorem", 80, 75),
    (r'\brandom\s*variable', 'Random Variables', 40, 10),
    (r'\bprobability\s*distribution', 'Probability Dist.', 60, 10),
    (r'\bexpected\s*value|\bE\[', 'Expected Value', 40, 25),
    (r'\bvariance\b|\bVar\(', 'Variance', 60, 25),
    (r'\bstandard\s*deviation', 'Std Deviation', 80, 20),
    (r'\bbayes\s*theorem|\bbayes.\s*rule', "Bayes' Theorem", 50, 40),
    (r'\bconditional\s*probability', 'Conditional Prob.', 30, 40),
    (r'\bindependen', 'Independence', 70, 40),
    (r'\bnormal\s*distribution|\bgaussian', 'Normal Distribution', 50, 55),
    (r'\bbinomial\s*distribution', 'Binomial Dist.', 25, 55),
    (r'\bpoisson\s*distribution', 'Poisson Dist.', 75, 55),
    (r'\bcentral\s*limit\s*theorem', 'Central Limit Theorem', 50, 70),
    (r'\bmoment\s*generat|\bMGF\b', 'MGF', 35, 70),
    (r'\bcumulative\s*dist|\bCDF\b', 'CDF', 65, 70),
    (r'\bpdf\b|probability\s*density', 'PDF', 50, 85),
    (r'\bhypothesis\s*test', 'Hypothesis Testing', 30, 85),
    (r'\bconfidence\s*interval', 'Confidence Interval', 70, 85),
    (r'\bmarkov\s*chain', 'Markov Chains', 50, 95),
    (r'\beigenvalue|\beigenvector', 'Eigenvalues / Vectors', 40, 20),
    (r'\bmatrix\s*multiplication|\bmatrix\s*product', 'Matrix Operations', 60, 20),
    (r'\blinear\s*(in)?dependen', 'Linear Independence', 20, 35),
    (r'\bspan\b.*vector|\bvector\s*space', 'Vector Spaces', 80, 35),
    (r'\borthogon', 'Orthogonality', 50, 50),
    (r'\bsingular\s*value|\bSVD\b', 'SVD', 50, 65),
    (r'\bdeterminant\b', 'Determinant', 30, 65),
    (r'\binverse\s*matrix', 'Matrix Inverse', 70, 65),
    (r'\bdifferential\s*equation', 'Differential Eqns', 25, 65),
    (r'\btaylor\s*series', 'Taylor Series', 70, 25),
    (r'\bderivative|\bdifferentiation', 'Derivatives', 45, 40),
    (r'\bintegral|\bintegration', 'Integration', 55, 40),
    (r'\bgradient\b', 'Gradient', 50, 30),
    (r'\bpartial\s*derivative', 'Partial Derivatives', 70, 40),
    (r'\bneural\s*network', 'Neural Networks', 50, 10),
    (r'\bgradient\s*descent', 'Gradient Descent', 30, 25),
    (r'\bbackpropagation', 'Backpropagation', 70, 25),
    (r'\boverfitting|\bunderfitting', 'Overfitting', 50, 40),
    (r'\bregularization|\bregularisation', 'Regularization', 50, 55),
    (r'\bsupport\s*vector|\bSVM\b', 'SVM', 20, 40),
    (r'\bdecision\s*tree', 'Decision Trees', 80, 40),
    (r'\brandom\s*forest', 'Random Forest', 80, 55),
    (r'\bk.means|\bclustering', 'Clustering', 20, 55),
    (r'\bprincipal\s*component|\bPCA\b', 'PCA', 50, 70),
    (r'\bconvolutional\s*neural|\bCNN\b', 'CNN', 30, 70),
    (r'\brecurrent\s*neural|\bRNN\b|\bLSTM\b', 'RNN / LSTM', 70, 70),
    (r'\battention\s*mechanism|\btransformer\b', 'Transformers', 50, 85),
    (r'\bloss\s*function', 'Loss Functions', 35, 85),
    (r'\bactivation\s*function', 'Activation Functions', 65, 85),
]

_DEPENDENCIES = [
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
    ('Derivatives', 'Differential Eqns'),
    ('Integration', 'Differential Eqns'),
    ('Derivatives', 'Partial Derivatives'),
    ('Partial Derivatives', 'Gradient'),
    ('Eigenvalues / Vectors', 'Matrix Operations'),
    ('Matrix Operations', 'SVD'),
    ('Linear Independence', 'Vector Spaces'),
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
]


def extract_concepts(note_text: str) -> dict:
    text_lower = note_text.lower()
    found = []
    seen_labels = set()
    node_id = 1

    for pattern, label, x, y in _CONCEPT_PATTERNS:
        if label in seen_labels:
            continue
        if re.search(pattern, text_lower):
            found.append({"id": node_id, "label": label, "status": "partial", "x": x, "y": y})
            seen_labels.add(label)
            node_id += 1

    edges = []
    label_to_id = {n["label"]: n["id"] for n in found}
    for src_label, dst_label in _DEPENDENCIES:
        if src_label in label_to_id and dst_label in label_to_id:
            edges.append([label_to_id[src_label], label_to_id[dst_label]])

    if not found:
        headings = re.findall(r'^#{1,3}\s+(.+)$', note_text, re.MULTILINE)
        candidates = [
            h.strip() for h in headings
            if 5 < len(h.strip()) < 50
            and not re.search(r'aura\s*graph|study\s*notes|proficiency', h, re.I)
        ]
        for i, label in enumerate(candidates[:12]):
            col = i % 3
            row = i // 3
            found.append({'id': i + 1, 'label': label[:30], 'status': 'partial', 'x': 20 + col * 30, 'y': 15 + row * 25})
        if found:
            edges = [[i, i + 1] for i in range(1, len(found))]
        else:
            found = [{'id': 1, 'label': 'Core Concept', 'status': 'partial', 'x': 50, 'y': 50}]

    return {'nodes': found, 'edges': edges}
