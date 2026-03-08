"""routers/notebooks.py — /notebooks/* CRUD + sections."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

import deps
from deps import get_current_user, _require_notebook_owner, _is_azure_available, _is_groq_available, _azure_chat, _groq_chat
from schemas import (
    NotebookCreateRequest, NotebookUpdateRequest,
    SectionCreateRequest, SectionUpdateRequest, SectionReorderRequest, SectionGenerateRequest,
)

logger = logging.getLogger("auragraph")
router = APIRouter(tags=["notebooks"])


@router.post("/notebooks")
async def new_notebook(req: NotebookCreateRequest, authorization: Optional[str] = Header(None)):
    from agents.notebook_store import create_notebook
    user = get_current_user(authorization)
    return create_notebook(user["id"], req.name, req.course)


@router.get("/notebooks")
async def list_notebooks(
    authorization: Optional[str] = Header(None),
    limit: int = Query(default=50, ge=1, le=200, description="Max notebooks to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    """
    Returns the caller's notebooks, newest first.
    Use `limit` and `offset` for pagination — e.g. `?limit=20&offset=40`.
    """
    from agents.notebook_store import get_notebooks
    user = get_current_user(authorization)
    all_nbs = get_notebooks(user["id"])
    # get_notebooks returns list; slice for pagination
    total   = len(all_nbs)
    page    = all_nbs[offset: offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "notebooks": page}


@router.get("/notebooks/{nb_id}")
async def fetch_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    return _require_notebook_owner(nb_id, user)


@router.patch("/notebooks/{nb_id}/note")
async def save_notebook_note(
    nb_id: str, req: NotebookUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.notebook_store import update_notebook_note
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    async with deps._db_write_lock:
        return update_notebook_note(nb_id, req.note, req.proficiency)


@router.delete("/notebooks/{nb_id}")
async def remove_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    from agents.notebook_store import delete_notebook
    from agents.knowledge_store import delete_notebook_store
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    delete_notebook(nb_id)
    delete_notebook_store(nb_id)
    try:
        from pipeline.vector_db import VectorDB
        VectorDB.delete(nb_id)
    except Exception:
        pass
    return {"status": "deleted"}


@router.get("/notebooks/{nb_id}/knowledge-stats")
async def get_knowledge_stats(nb_id: str, authorization: Optional[str] = Header(None)):
    from agents.knowledge_store import get_chunk_stats
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    return get_chunk_stats(nb_id)


# ── Sections ───────────────────────────────────────────────────────────────────

@router.get("/notebooks/{nb_id}/sections")
async def list_sections(nb_id: str, authorization: Optional[str] = Header(None)):
    from agents.notebook_store import get_sections
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    return get_sections(nb_id)


@router.post("/notebooks/{nb_id}/sections")
async def add_section(
    nb_id: str, req: SectionCreateRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.notebook_store import create_section
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    return create_section(nb_id, req.title, req.note_type)


@router.patch("/notebooks/{nb_id}/sections/{section_id}")
async def edit_section(
    nb_id: str, section_id: str, req: SectionUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.notebook_store import update_section
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    updates = req.model_dump(exclude_none=True)
    result  = update_section(section_id, **updates)
    if not result:
        raise HTTPException(404, "Section not found")
    return result


@router.delete("/notebooks/{nb_id}/sections/{section_id}")
async def remove_section(
    nb_id: str, section_id: str,
    authorization: Optional[str] = Header(None),
):
    from agents.notebook_store import delete_section
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    if not delete_section(section_id):
        raise HTTPException(404, "Section not found")
    return {"status": "deleted"}


@router.put("/notebooks/{nb_id}/sections/reorder")
async def reorder_notebook_sections(
    nb_id: str, req: SectionReorderRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.notebook_store import reorder_sections
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    return reorder_sections(nb_id, req.order)


@router.post("/notebooks/{nb_id}/sections/{section_id}/generate")
async def generate_section_note(
    nb_id: str, section_id: str, req: SectionGenerateRequest,
    authorization: Optional[str] = Header(None),
):
    """Generate LLM note content for a single section topic."""
    from agents.notebook_store import get_section, update_section, rebuild_note_from_sections, update_notebook_note
    from agents.latex_utils import fix_latex_delimiters
    user = get_current_user(authorization)
    nb   = _require_notebook_owner(nb_id, user)
    sec  = get_section(section_id)
    if not sec or sec["notebook_id"] != nb_id:
        raise HTTPException(404, "Section not found")

    topic_prompt = (
        f"You are generating a detailed study note for the topic: **{sec['title']}**\n"
        f"Course context: {nb.get('name', '')} ({nb.get('course', '')})\n"
        f"Student proficiency level: {req.proficiency}\n\n"
        "Write a comprehensive yet focused note covering key concepts, examples, and "
        "any important formulas or definitions. Use Markdown with ## headings, bullet lists, "
        "and LaTeX math where appropriate (delimited by $...$ or $$...$$)."
    )
    messages = [
        {"role": "system", "content": "You are an expert academic note writer. Produce well-structured Markdown notes."},
        {"role": "user", "content": topic_prompt},
    ]
    content = ""
    if _is_azure_available():
        try:
            content = await _azure_chat(messages, max_tokens=2048)
        except Exception as e:
            logger.warning("Azure section generate failed: %s", e)
    if not content and _is_groq_available():
        try:
            content = await _groq_chat(messages, max_tokens=2048)
        except Exception as e:
            logger.warning("Groq section generate failed: %s", e)
    if not content:
        raise HTTPException(503, "LLM unavailable — cannot generate section note")

    from pipeline.note_generator import _fix_tables
    content = fix_latex_delimiters(_fix_tables(content))
    updated = update_section(section_id, content=content)
    full_note = rebuild_note_from_sections(nb_id)
    update_notebook_note(nb_id, full_note, req.proficiency or nb.get("proficiency"))
    return updated


# ── Notebook-scoped graph ──────────────────────────────────────────────────────

@router.get("/notebooks/{nb_id}/graph")
async def get_notebook_graph(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb   = _require_notebook_owner(nb_id, user)
    return nb.get("graph", {"nodes": [], "edges": []})


@router.post("/notebooks/{nb_id}/graph/update")
async def update_notebook_graph_node(
    nb_id: str,
    req: "NodeUpdateRequest",
    authorization: Optional[str] = Header(None),
):
    from schemas import NodeUpdateRequest  # local import avoids circular at module level
    from agents.notebook_store import update_notebook_graph
    user  = get_current_user(authorization)
    nb    = _require_notebook_owner(nb_id, user)
    graph = nb.get("graph", {"nodes": [], "edges": []})
    for node in graph["nodes"]:
        if node["label"].lower() == req.concept_name.lower():
            node["status"] = req.status
            update_notebook_graph(nb_id, graph)
            return {"status": "success", "node": node}
    raise HTTPException(404, "Concept node not found")
