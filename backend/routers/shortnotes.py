"""routers/shortnotes.py — AI-generated cheatsheet / summary notes per notebook."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import deps
from deps import get_current_user, _require_notebook_owner, _check_llm_rate_limit, _record_llm_call

logger = logging.getLogger("auragraph")
router = APIRouter(tags=["shortnotes"])


_SHORT_NOTES_SYSTEM = """\
You are AuraGraph's Cheatsheet Engine — a concise, exam-focused note synthesiser.

You receive a student's full notes, their highlights, doubts they raised, their
mastery status per concept, and their proficiency level.

Your job: generate a PERFECT one-page cheatsheet the student can review in 10 minutes
before an exam. This is NOT a summary — it is an intelligent distillation that:

1. Prioritises what the student found difficult (struggling concepts, raised doubts)
2. Reinforces what they highlighted as important (blend naturally into concepts/tips)
3. Includes every essential formula, definition, and diagram description
4. Skips verbose explanations — use dense, tight bullet points
5. Calibrates depth to their proficiency level
6. If highlights are present, explicitly prioritise them in Key Concepts and Exam Tips

OUTPUT FORMAT (strict Markdown, no deviations):
# ⚡ Quick Review: {notebook_name}
*{proficiency} level · {concept_count} concepts*

## 🔑 Key Concepts & Definitions
[2–3 line bullets per major concept — definition + one key property]

## 📐 Essential Formulas
[LaTeX display math for every important formula — name it, show it, add a one-line note]

## ⚠️ Watch Out (Common Mistakes)
[Based on the student's doubts — reframe each doubt as a trap to avoid]

## 🎯 Weak Areas to Revise
[Concepts with status=struggling or partial — brief note on what to focus on]

## 💡 Exam Tips
[3–5 sharp, actionable tips based on the material and student's level]

Rules:
- Use LaTeX: inline $...$ and display $$...$$ on its own line
- Keep each section tight — never more than 8 bullets
- Do NOT reproduce the full notes — distil them
- Treat student highlights as high-priority revision anchors; weave them into key bullets.
- Output ONLY the Markdown — no preamble, no "Here is your cheatsheet:"
"""

_SHORT_NOTES_USER = """\
STUDENT PROFILE:
- Notebook: {notebook_name}
- Course: {course}
- Proficiency level: {proficiency}
- Concept mastery: {mastery_summary}

LEARNER PERSONALISATION CONTEXT:
{learner_context}

CONCEPTS WITH STATUS:
{concept_statuses}

DOUBTS THE STUDENT RAISED (address these as traps/tips):
{doubts_text}

STUDENT HIGHLIGHTS (use only when relevant; do not create a separate Highlights section):
{highlights_text}

HIGHLIGHT PRIORITY:
- Total highlights available: {highlights_count}
- If highlights exist, ensure the generated notes clearly reflect them in concepts/tips/formulas where relevant.

FULL NOTES (distil these — do not reproduce verbatim):
{notes_truncated}

Generate the cheatsheet now.
"""


class ShortNotesResponse(BaseModel):
    content: str = ""
    source: str = ""
    updated_at: str = ""
    has_previous: bool = False
    preview_mode: str = "latest"


@router.get("/api/notebooks/{nb_id}/short-notes", response_model=ShortNotesResponse)
async def get_short_notes(
    nb_id: str,
    authorization: Optional[str] = Header(None),
):
    from agents.notebook_store import get_short_note

    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    current = get_short_note(nb_id)
    return ShortNotesResponse(
        content=current.get("content", ""),
        source=current.get("source", ""),
        updated_at=current.get("updated_at", ""),
        has_previous=bool(current.get("has_previous")),
        preview_mode="latest",
    )


@router.post("/api/notebooks/{nb_id}/short-notes")
async def generate_short_notes(
    nb_id: str,
    authorization: Optional[str] = Header(None),
):
    """Generate AI cheatsheet for a notebook. Returns SSE stream."""
    from agents.notebook_store import get_notebook, get_doubts, get_annotations, save_short_note
    from agents.mastery_store import get_db
    from agents.behaviour_store import get_personalisation_context
    from agents.auth_utils import get_user_profile, profile_to_student_context

    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    _check_llm_rate_limit(user["id"])

    nb = get_notebook(nb_id)
    if not nb:
        raise HTTPException(404, "Notebook not found.")

    note    = nb.get("note", "") or ""
    prof    = nb.get("proficiency", "Practitioner")
    name    = nb.get("name", "Notebook")
    course  = nb.get("course", "")

    # ── Mastery graph from Cosmos DB / SQLite ──────────────────────────────
    graph_data = get_db(user["id"])
    nodes = graph_data.get("nodes", [])
    # Also merge nodes from the notebook's own graph (more current)
    nb_nodes = (nb.get("graph") or {}).get("nodes", [])
    if nb_nodes:
        nodes = nb_nodes

    mastered   = [n for n in nodes if n.get("status") == "mastered"]
    partial    = [n for n in nodes if n.get("status") == "partial"]
    struggling = [n for n in nodes if n.get("status") == "struggling"]

    mastery_summary = (
        f"{len(mastered)} mastered, {len(partial)} partial, "
        f"{len(struggling)} struggling out of {len(nodes)} total"
    )
    concept_statuses = "\n".join(
        f"- {n.get('full_label') or n.get('label','?')}: {n.get('status','?')}"
        for n in nodes[:40]
    ) or "(no concept data)"

    # ── Doubts ────────────────────────────────────────────────────────────
    doubts   = get_doubts(nb_id)
    doubts_text = "\n".join(
        f"- Page {d.get('pageIdx',0)+1}: \"{d.get('doubt','')}\" "
        f"→ {d.get('insight','')[:120]}"
        for d in doubts[:20]
    ) or "(no doubts recorded)"

    # ── Highlights ────────────────────────────────────────────────────────
    anns = get_annotations(nb_id)

    def _extract_highlight_text(ann: dict) -> str:
        data = ann.get("data") or {}
        if not isinstance(data, dict):
            return ""

        # Current frontend highlight payload uses `selectedText`.
        # Keep compatibility with older/alternate keys.
        for key in ("selectedText", "text", "quote", "content", "highlightText"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

        fragments = data.get("fragments")
        if isinstance(fragments, list):
            joined = " ".join(str(x).strip() for x in fragments if str(x).strip()).strip()
            if joined:
                return joined

        return ""

    highlights = []
    seen_highlights = set()
    for ann in anns:
        if ann.get("type") != "highlight":
            continue
        txt = _extract_highlight_text(ann)
        if not txt:
            continue
        norm = " ".join(txt.lower().split())
        if norm in seen_highlights:
            continue
        seen_highlights.add(norm)
        highlights.append(txt)

    highlights_text = "\n".join(f"- \"{h}\"" for h in highlights[:30]) or "(no highlights)"

    # ── Notes (truncate to fit context) ───────────────────────────────────
    notes_truncated = note[:12000] + ("…[truncated]" if len(note) > 12000 else "")

    learner_ctx = ""
    try:
        import asyncio as _aio
        beh_ctx = await _aio.to_thread(get_personalisation_context, user["id"])
        edu_profile = await _aio.to_thread(get_user_profile, user["id"])
        edu_ctx = profile_to_student_context(edu_profile, proficiency=prof)
        learner_ctx = "\n".join([x for x in [beh_ctx, edu_ctx] if x and x.strip()]) or "(none)"
    except Exception:
        learner_ctx = "(none)"

    user_prompt = _SHORT_NOTES_USER.format(
        notebook_name=name,
        course=course or "General",
        proficiency=prof,
        mastery_summary=mastery_summary,
        learner_context=learner_ctx,
        concept_statuses=concept_statuses,
        doubts_text=doubts_text,
        highlights_text=highlights_text,
        highlights_count=len(highlights),
        notes_truncated=notes_truncated,
    )

    messages = [
        {"role": "system", "content": _SHORT_NOTES_SYSTEM},
        {"role": "user",   "content": user_prompt},
    ]

    # ── Stream the cheatsheet ─────────────────────────────────────────────
    async def _stream():
        import json as _j
        raw = None
        source = "local"
        if deps._is_azure_available():
            try:
                raw = await deps._azure_chat(messages, max_tokens=3000)
                if raw:
                    source = "azure"
            except Exception as e:
                logger.warning("short-notes Azure failed: %s", e)
        if not raw and deps._is_groq_available():
            try:
                raw = await deps._groq_chat(messages, max_tokens=3000)
                if raw:
                    source = "groq"
            except Exception as e:
                logger.warning("short-notes Groq failed: %s", e)
        if not raw:
            raw = f"# ⚡ Quick Review: {name}\n\n*Could not reach AI — try again.*"
            source = "local"

        if source in ("azure", "groq"):
            _record_llm_call(user["id"], source, est_tokens=3000)

        saved = save_short_note(nb_id, raw, source=source)

        yield f"data: {_j.dumps({'content': raw, 'source': source, 'has_previous': bool(saved.get('has_previous')), 'preview_mode': 'latest', 'done': True})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/api/notebooks/{nb_id}/short-notes/undo-preview", response_model=ShortNotesResponse)
async def undo_short_notes_preview(
    nb_id: str,
    authorization: Optional[str] = Header(None),
):
    """Preview previous short-notes snapshot without modifying saved latest."""
    from agents.notebook_store import get_short_note_previous

    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)

    prev = get_short_note_previous(nb_id)
    if not prev.get("content"):
        raise HTTPException(404, "No previous short notes snapshot available.")

    return ShortNotesResponse(
        content=prev.get("content", ""),
        source=prev.get("source", ""),
        updated_at=prev.get("updated_at", ""),
        has_previous=True,
        preview_mode="undo",
    )


@router.post("/api/notebooks/{nb_id}/short-notes/redo-preview", response_model=ShortNotesResponse)
async def redo_short_notes_preview(
    nb_id: str,
    authorization: Optional[str] = Header(None),
):
    """Return latest saved short notes after an undo preview."""
    from agents.notebook_store import get_short_note

    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)

    current = get_short_note(nb_id)
    if not current.get("content"):
        raise HTTPException(404, "No short notes found yet.")

    return ShortNotesResponse(
        content=current.get("content", ""),
        source=current.get("source", ""),
        updated_at=current.get("updated_at", ""),
        has_previous=bool(current.get("has_previous")),
        preview_mode="latest",
    )
