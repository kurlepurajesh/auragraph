"""
test_notes_pipeline.py
─────────────────────
Comprehensive smoke-tests for the notes generation pipeline.

Runs WITHOUT pytest — just:
    python test_notes_pipeline.py

Tests:
  1. _strip_metadata_lines  — metadata removed, content preserved
  2. extract_text_from_pptx — author/institution slide skipped,
                               content slides present & well-formed
  3. fix_latex_delimiters   — all 4 variants correctly normalised
  4. Page splitter (Python   — mirrors the JS logic)
  5. /api/upload-fuse-multi  — live endpoint (POST with synthetic PPTX)
  6. /api/fuse               — direct JSON fusion (plain text, no files)
"""

from __future__ import annotations

import io
import sys
import json
import traceback
import textwrap
import re

# ── colour helpers ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = failed = skipped = 0

def ok(name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  {GREEN}✓{RESET} {name}" + (f" — {detail}" if detail else ""))

def fail(name: str, detail: str):
    global failed
    failed += 1
    print(f"  {RED}✗{RESET} {BOLD}{name}{RESET}")
    for line in detail.splitlines():
        print(f"      {line}")

def skip(name: str, reason: str):
    global skipped
    skipped += 1
    print(f"  {YELLOW}?{RESET} {name} (skipped: {reason})")

def section(title: str):
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. _strip_metadata_lines
# ═══════════════════════════════════════════════════════════════════════════
section("1 · _strip_metadata_lines")
sys.path.insert(0, ".")
from agents.pdf_utils import _strip_metadata_lines   # type: ignore

META_CASES = [
    # (input line, should_be_kept)
    ("john.doe@iitb.ac.in",        False),
    ("Dr. Rajesh Kumar",            False),
    ("Prof. Arun Singh",            False),
    ("Indian Institute of Technology Delhi", False),
    ("Department of Electronics",   False),
    ("May 2024",                    False),
    ("01/03/2026",                  False),
    # Content that MUST be kept
    ("The Fourier Transform is defined as:", True),
    ("• Linearity: F{af+bg} = aF{f} + bF{g}", True),
    ("x(t) = A cos(2\\pi f_0 t)",    True),
    ("$E = mc^2$",                   True),
    ("Convolution is associative and commutative.", True),
    ("1. Compute the DFT of x[n].",  True),
]

for line, keep in META_CASES:
    result = _strip_metadata_lines(line).strip()
    kept = bool(result)
    if kept == keep:
        ok(repr(line)[:60], "kept" if keep else "stripped")
    else:
        fail(repr(line)[:60],
             f"Expected {'kept' if keep else 'stripped'} but got {'kept' if kept else 'stripped'}\n  result={repr(result)}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. extract_text_from_pptx — synthetic PPTX
# ═══════════════════════════════════════════════════════════════════════════
section("2 · extract_text_from_pptx (synthetic PPTX)")

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from agents.pdf_utils import extract_text_from_pptx  # type: ignore

    def make_pptx() -> bytes:
        prs = Presentation()
        blank_layout = prs.slide_layouts[6]  # blank

        # Slide 1 — title/author metadata slide
        slide1 = prs.slides.add_slide(prs.slide_layouts[0])
        slide1.shapes.title.text = "Digital Signal Processing"
        ph = slide1.placeholders[1]
        ph.text = "Dr. Ravi Shankar\nravi@iitb.ac.in\nDepartment of EE, IIT Bombay\nMarch 2026"

        # Slide 2 — real content
        slide2 = prs.slides.add_slide(prs.slide_layouts[1])
        slide2.shapes.title.text = "Discrete Fourier Transform"
        ph2 = slide2.placeholders[1]
        tf = ph2.text_frame
        tf.text = "The DFT converts a finite sequence to frequency domain."
        p = tf.add_paragraph()
        p.text = "X[k] = sum_{n=0}^{N-1} x[n] e^{-j2pi kn/N}"

        # Slide 3 — another content slide
        slide3 = prs.slides.add_slide(prs.slide_layouts[1])
        slide3.shapes.title.text = "Convolution Theorem"
        ph3 = slide3.placeholders[1]
        ph3.text_frame.text = "Circular convolution in time equals multiplication in frequency."

        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()

    pptx_bytes = make_pptx()
    extracted = extract_text_from_pptx(pptx_bytes)

    # 2a — slide markers present
    if "--- Slide 1" in extracted and "--- Slide 2" in extracted and "--- Slide 3" in extracted:
        ok("Slide boundary markers all present")
    else:
        fail("Slide boundary markers", f"Got:\n{extracted[:300]}")

    # 2b — content slides present
    if "Discrete Fourier Transform" in extracted and "Convolution Theorem" in extracted:
        ok("Content slide titles present")
    else:
        fail("Content slide titles", f"Missing in:\n{extracted[:400]}")

    # 2c — author metadata stripped from body
    metadata_leaks = [s for s in ["ravi@iitb.ac.in", "Dr. Ravi Shankar", "IIT Bombay"]
                      if s in extracted]
    if not metadata_leaks:
        ok("Author/email metadata stripped from slide body")
    else:
        fail("Author metadata stripping", f"Still present: {metadata_leaks}\n---\n{extracted[:500]}")

    # 2d — DFT content formula line is kept
    if "X[k]" in extracted or "DFT" in extracted:
        ok("Content formula/text kept in slide body")
    else:
        fail("Content preservation", f"DFT formula missing:\n{extracted}")

except Exception as e:
    fail("extract_text_from_pptx", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════════════════
# 3. fix_latex_delimiters
# ═══════════════════════════════════════════════════════════════════════════
section("3 · fix_latex_delimiters")
from agents.latex_utils import fix_latex_delimiters  # type: ignore

LATEX_CASES = [
    # (description, input, expected_pattern, pattern_is_regex)

    # \\(...\\) → $...$  (no spaces)
    ("inline \\(…\\) → $…$",
     r"The transform \(F(\omega)\) is defined",
     r"\$F\(\\omega\)\$", True),

    # multi-line inline
    ("multi-line \\(…\\) → $…$",
     "value is \\(\n  x^2\n\\) here",
     r"\$x\^2\$", True),

    # \\[…\\] → block $$
    ("display \\[…\\] → block $$",
     "formula:\n\\[\n  E = mc^2\n\\]",
     r"\$\$\nE = mc\^2\n\$\$", True),

    # single-line $$x$$ → block
    ("single-line $$…$$ → block",
     "so $$x^2 + y^2 = r^2$$ is it",
     r"\$\$\nx\^2 \+ y\^2 = r\^2\n\$\$", True),

    # no spaces inside $ delimiters for inline
    ("no leading/trailing space in $…$",
     r"the value \(   \alpha   \) is small",
     r'\$\\alpha\$', True),

    # existing good $…$ must not be double-converted
    ("do not double-convert existing $…$",
     "value is $x^2$ already",
     "$x^2$", False),
]

for desc, src, expected, is_re in LATEX_CASES:
    try:
        result = fix_latex_delimiters(src)
        if is_re:
            match = re.search(expected, result)
        else:
            match = expected in result
        if match:
            ok(desc)
        else:
            fail(desc, f"Pattern not found: {expected!r}\nResult: {repr(result)}")
    except Exception as e:
        fail(desc, str(e))


# ═══════════════════════════════════════════════════════════════════════════
# 4. Page splitter (Python mirror of JS logic)
# ═══════════════════════════════════════════════════════════════════════════
section("4 · Page splitter (Python mirror of JS)")

def js_page_splitter(note: str, target: int = 2200) -> list[str]:
    """Mirrors the useMemo pages logic from NotebookWorkspace.jsx."""
    if not note:
        return []
    # Split by ## headings
    by_h2 = [s.strip() for s in re.split(r'(?=^## )', note, flags=re.MULTILINE) if s.strip()]
    if by_h2:
        merged, buf = [], ''
        for s in by_h2:
            if buf and len(buf) + len(s) + 2 > target and len(buf) > 500:
                merged.append(buf.strip())
                buf = s
            else:
                buf = (buf + '\n\n' + s) if buf else s
        if buf:
            merged.append(buf.strip())
        return [p for p in merged if p]
    # fallback — not testing this branch here
    return [note]

NOTE_15_SECTIONS = "\n\n".join(
    f"## Topic {i}\n" + ("Content about topic. " * 30)   # ~180 chars each
    for i in range(1, 16)
)

pages = js_page_splitter(NOTE_15_SECTIONS)
if 3 <= len(pages) <= 7:
    ok(f"15 sections → {len(pages)} pages (expected 3–7)")
else:
    fail(f"15 sections → {len(pages)} pages", "Expected 3–7 pages, not one-per-section or 1 giant page")

# 4b — math block is never split across pages
MATH_NOTE = "## Calculus\n\nThe integral is:\n\n$$\n\\int_0^\\infty e^{-x} dx = 1\n$$\n\nThis converges absolutely.\n\n## " + \
            "\n\n".join(f"## Section {i}\n" + "Filler text. " * 50 for i in range(1, 10))
pages2 = js_page_splitter(MATH_NOTE)
broken = any(p.count('$$') % 2 != 0 for p in pages2)
if not broken:
    ok("No $$ block split across pages")
else:
    fail("$$ block split across pages",
         "\n".join(f"Page {i}: {p.count('$$')} $$ markers" for i, p in enumerate(pages2)))


# ═══════════════════════════════════════════════════════════════════════════
# 5. Live API — /api/upload-fuse-multi
# ═══════════════════════════════════════════════════════════════════════════
section("5 · Live API /api/upload-fuse-multi")
try:
    import requests

    # Reuse the synthetic PPTX from test 2 as "slides"
    # Build a minimal PDF for "textbook" using bytes (single blank page trick)
    MINIMAL_PDF = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 720 Td (Textbook content here.) Tj ET\nendstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n441\n%%EOF"
    )

    files = {
        "slides_pdfs":   ("slides.pptx",   pptx_bytes,    "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        "textbook_pdfs": ("textbook.pdf",  MINIMAL_PDF,   "application/pdf"),
    }
    data = {"proficiency": "Intermediate"}

    resp = requests.post("http://localhost:8000/api/upload-fuse-multi",
                         files=files, data=data, timeout=60)

    if resp.status_code == 200:
        body = resp.json()
        note = body.get("fused_note", "")
        if note.strip():
            ok(f"HTTP 200, note length={len(note)} chars")
        else:
            fail("HTTP 200 but fused_note is empty", str(body)[:200])

        # 5b — no raw metadata in output
        meta_in_note = [s for s in ["ravi@iitb.ac.in", "Dr. Ravi Shankar", "IIT Bombay"]
                        if s in note]
        if not meta_in_note:
            ok("No metadata leaking into LLM output")
        else:
            fail("Metadata leaked into fused_note", f"Found: {meta_in_note}")

        # 5c — has markdown headings
        if re.search(r'^##\s', note, re.MULTILINE):
            ok("Output contains ## headings (proper markdown structure)")
        else:
            fail("No ## headings in output", f"First 300 chars:\n{note[:300]}")

        # 5d — no raw \\( or \\[ in output
        bad_delims = [d for d in [r'\(', r'\)', r'\[', r'\]'] if d in note]
        if not bad_delims:
            ok("No raw \\( \\) \\[ \\] delimiters in output")
        else:
            fail("Raw LaTeX delimiters found", f"{bad_delims} still present")

    elif resp.status_code == 503:
        skip("/api/upload-fuse-multi", "Azure OpenAI not configured (503 — using local fallback check)")
        # With no API key the local fallback should still return something
        if resp.status_code == 503:
            resp2 = requests.post("http://localhost:8000/api/fuse",
                json={"slide_summary": "DFT: X[k] = sum x[n] e^{-j2pi kn/N}",
                      "textbook_paragraph": "The DFT maps a sequence to frequency domain.",
                      "proficiency": "Intermediate"}, timeout=30)
            if resp2.status_code in (200, 503):
                skip("Fuse endpoint reachable", "/api/fuse returned " + str(resp2.status_code))
    else:
        fail(f"/api/upload-fuse-multi HTTP {resp.status_code}", resp.text[:400])

except ImportError:
    skip("/api/upload-fuse-multi", "requests not installed")
except Exception as e:
    fail("/api/upload-fuse-multi", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════════════════
# 6. /api/fuse — direct JSON with latex-heavy content
# ═══════════════════════════════════════════════════════════════════════════
section("6 · Live API /api/fuse (direct JSON)")
try:
    import requests

    SLIDE_TEXT = textwrap.dedent("""\
        --- Slide 1: Fourier Transform ---
        Converts time-domain signal to frequency domain.
        Formula: F(omega) = integral x(t) e^{-j omega t} dt

        --- Slide 2: Properties ---
        Linearity: F{af + bg} = aF{f} + bF{g}
        Time-shifting: F{x(t-t0)} = e^{-j omega t0} F{omega}
    """)

    TEXTBOOK_TEXT = textwrap.dedent("""\
        The Fourier Transform decomposes a signal into its constituent
        sinusoidal frequencies. It is widely used in signal processing,
        communications, and solving differential equations.
        The inverse transform is: x(t) = (1/2pi) integral F(omega) e^{jwt} domega
    """)

    resp = requests.post(
        "http://localhost:8000/api/fuse",
        json={"slide_summary": SLIDE_TEXT,
              "textbook_paragraph": TEXTBOOK_TEXT,
              "proficiency": "Beginner"},
        timeout=40,
    )

    if resp.status_code == 200:
        body = resp.json()
        note = body.get("fused_note", "")
        if note.strip():
            ok(f"HTTP 200, note length={len(note)} chars")
        else:
            fail("fused_note is empty", str(body))

        # Check no raw \\( or \\[ left
        bad = [d for d in [r'\(', r'\)', r'\[', r'\]'] if d in note]
        if not bad:
            ok("latex_utils cleaned all delimiters")
        else:
            fail("Raw delimiters still present", str(bad))

        # Should have exam tip
        if "Exam Tip" in note:
            ok("Exam tip present in note")
        else:
            fail("Exam tip missing", f"First 600 chars:\n{note[:600]}")

    elif resp.status_code == 503:
        skip("/api/fuse", "Azure OpenAI not configured — local fallback only")
    else:
        fail(f"/api/fuse HTTP {resp.status_code}", resp.text[:300])

except ImportError:
    skip("/api/fuse", "requests not installed")
except Exception as e:
    fail("/api/fuse", traceback.format_exc())


# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{'═'*60}")
total = passed + failed + skipped
colour = GREEN if failed == 0 else RED
print(f"{BOLD}{colour}  {passed}/{total} passed  |  {failed} failed  |  {skipped} skipped{RESET}")
print(f"{'═'*60}\n")

if failed:
    sys.exit(1)
