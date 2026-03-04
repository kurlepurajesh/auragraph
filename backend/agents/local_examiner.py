import re

_QUESTION_BANK = {
    "fourier": [
        ("What does the Fourier Transform convert a signal from?",
         ["A) Frequency domain to spatial domain", "B) Time domain to frequency domain",
          "C) Spatial domain to time domain", "D) Amplitude domain to phase domain"],
         "B", "The Fourier Transform maps a time-domain signal to its frequency-domain representation."),
        ("Which property links time-domain convolution to frequency-domain multiplication?",
         ["A) Linearity property", "B) Duality property",
          "C) Convolution theorem", "D) Parseval's theorem"],
         "C", "The Convolution Theorem is the key property linking these operations."),
        ("What is the Fourier Transform of a Dirac delta function?",
         ["A) Zero for all frequencies", "B) A constant (1) for all frequencies",
          "C) A sinusoidal function", "D) An impulse at w=0"],
         "B", "The Dirac delta contains all frequencies equally."),
    ],
    "convolution": [
        ("What operation does convolution perform on two signals?",
         ["A) Pointwise multiplication",
          "B) Integration of the product of one signal with time-reversed shifted version of another",
          "C) Addition of two signals", "D) Differentiation of the product"],
         "B", "Convolution integrates the overlap between one signal and the flipped, shifted version of the second."),
        ("Which system property is most directly characterised by convolution?",
         ["A) Non-linear systems", "B) Time-varying systems",
          "C) Linear Time-Invariant (LTI) systems", "D) Causal non-LTI systems"],
         "C", "Convolution is the fundamental tool for analysing LTI systems."),
    ],
}

_GENERIC_QUESTIONS = [
    ("Which best describes the purpose of a mathematical transform in signal processing?",
     ["A) To amplify signals",
      "B) To convert a signal into another domain where analysis is simpler",
      "C) To encrypt data", "D) To generate new signals from noise"],
     "B", "Transforms change representation to a domain that reveals useful properties."),
    ("What is a key benefit of frequency-domain analysis?",
     ["A) It eliminates noise automatically",
      "B) It reveals spectral composition and allows simpler filtering",
      "C) It reduces computational complexity in all cases",
      "D) It makes signals time-invariant"],
     "B", "In the frequency domain, filtering becomes multiplication."),
    ("Which property allows output decomposition using superposition?",
     ["A) Time-invariance", "B) Causality",
      "C) Linearity", "D) Stability"],
     "C", "Linearity means the response to a sum equals the sum of individual responses."),
]


def _match_concept(concept_name):
    cl = concept_name.lower()
    for key, questions in _QUESTION_BANK.items():
        if key in cl:
            return questions
    return _GENERIC_QUESTIONS


def _format_questions(questions, concept_name):
    lines = [f"**Practice Questions: {concept_name}**\n"]
    for i, (q_text, options, correct, explanation) in enumerate(questions[:5], 1):
        lines.append(f"**Q{i}.** {q_text}")
        for opt in options:
            letter = opt[0]
            marker = " (Correct)" if letter == correct else ""
            lines.append(f"{opt}{marker}")
        lines.append(f"> **Explanation:** {explanation}")
        lines.append("")
    return "\n".join(lines).strip()


def local_examine(concept_name):
    questions = _match_concept(concept_name)
    return _format_questions(questions, concept_name)
