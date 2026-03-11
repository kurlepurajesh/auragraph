"""routers/learning.py — doubt, mutate, regenerate, examine, sniper-exam, concept-practice."""
from __future__ import annotations

import json as _json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

import deps
from deps import (
    get_current_user, _require_notebook_owner,
    _check_llm_rate_limit, _record_llm_call,
    _format_chunks_for_prompt, _note_to_pages,
)
from schemas import (
    DoubtRequest, DoubtResponse,
    MutationRequest, MutationResponse,
    RegenerateSectionRequest, RegenerateSectionResponse,
    SniperExamRequest, SniperExamResponse,
    GeneralExamRequest, GeneralExamResponse,
    ExaminerRequest, ExaminerResponse,
    ConceptPracticeRequest, ConceptPracticeResponse,
)

logger = logging.getLogger("auragraph")
router = APIRouter(tags=["learning"])


# ── Robust LLM JSON parser (handles LaTeX backslashes) ────────────────────────

def _parse_llm_json(text: str):
    """Parse JSON from LLM output, fixing LaTeX backslash issues.

    LLMs often produce unescaped LaTeX like \\theta which overlaps with JSON
    escape sequences (\\t = tab).  Two-pass: try raw first, then fix backslashes.
    """
    # Pass 1: direct parse
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass
    # Pass 2: protect already-valid escapes, then double remaining backslashes
    fixed = text
    fixed = fixed.replace('\\\\', '\x00DBL\x00')    # protect \\
    fixed = fixed.replace('\\"',  '\x00QT\x00')      # protect \"
    fixed = fixed.replace('\\',   '\\\\')             # double all remaining
    fixed = fixed.replace('\x00DBL\x00', '\\\\')     # restore \\
    fixed = fixed.replace('\x00QT\x00',  '\\"')      # restore \"
    try:
        return _json.loads(fixed)
    except _json.JSONDecodeError as exc:
        logger.warning("LLM JSON parse failed after backslash fix: %s", exc)
        return None


# ── Doubt answering ────────────────────────────────────────────────────────────

@router.post("/api/doubt", response_model=DoubtResponse)
async def answer_doubt(
    req: DoubtRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks, get_note_page
    from agents.verifier_agent import parse_verification_response
    from agents.content_safety import check_content_safety
    from agents.latex_utils import fix_latex_delimiters

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    _require_notebook_owner(req.notebook_id, user)

    slide_hits    = retrieve_relevant_chunks(req.notebook_id, req.doubt, top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(req.notebook_id, req.doubt, top_k=6, source_filter="textbook")
    slide_ctx    = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_ctx = _format_chunks_for_prompt(textbook_hits, 8_000)
    note_page    = get_note_page(req.notebook_id, req.page_idx) or ""

    raw_text: str | None = None
    source = "local"

    if deps._is_azure_available():
        try:
            raw_text = str(await deps.fusion_agent.answer_doubt(
                doubt=req.doubt, slide_context=slide_ctx,
                textbook_context=textbook_ctx, note_page=note_page,
            ))
            source = "azure"
        except Exception as e:
            logger.warning("Azure doubt failed: %s", e)

    if raw_text is None and deps._is_groq_available():
        try:
            raw_text = await deps._groq_doubt(req.doubt, slide_ctx, textbook_ctx, note_page)
            source   = "groq"
        except Exception as e:
            logger.warning("Groq doubt failed: %s", e)

    if raw_text is not None:
        vr = parse_verification_response(raw_text)
        _safe, _cat = await check_content_safety(vr.answer)
        if not _safe:
            logger.warning("Content Safety flagged doubt answer: category=%s", _cat)
        _record_llm_call(user["id"], source, est_tokens=1500)
        return DoubtResponse(
            answer=fix_latex_delimiters(vr.answer),
            source=source,
            verification_status=vr.verification_status,
            correction=fix_latex_delimiters(vr.correction),
            footnote=vr.footnote,
        )

    from agents.local_mutation import _diagnose_gap, _build_analogy_hint
    gap     = _diagnose_gap(req.doubt)
    analogy = _build_analogy_hint(req.doubt)
    answer  = f"**{gap}**\n\n{analogy}"
    if note_page:
        answer += f"\n\n*From your notes:* {note_page[:300]}…"
    return DoubtResponse(answer=fix_latex_delimiters(answer), source="local")


# ── Mutation ───────────────────────────────────────────────────────────────────

@router.post("/api/mutate", response_model=MutationResponse)
async def mutate_note(
    req: MutationRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks, get_note_page, update_note_page, get_all_note_pages
    from agents.notebook_store import update_notebook_note
    from agents.mastery_store import update_node_status, increment_mutation_count
    from agents.content_safety import check_content_safety
    from agents.local_mutation import local_mutate
    from agents.concept_extractor import extract_concepts
    from agents.latex_utils import fix_latex_delimiters
    from pipeline.note_generator import _fix_tables

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    _require_notebook_owner(req.notebook_id, user)
    _username = user["id"]

    note_page = get_note_page(req.notebook_id, req.page_idx)
    if note_page is None:
        note_page = req.original_paragraph or ""

    query         = req.doubt + " " + note_page[:200]
    slide_hits    = retrieve_relevant_chunks(req.notebook_id, query, top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(req.notebook_id, query, top_k=6, source_filter="textbook")
    slide_ctx     = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_ctx  = _format_chunks_for_prompt(textbook_hits, 8_000)

    mutated, gap, answer, llm_source = await deps._llm_mutate(note_page, req.doubt, slide_ctx, textbook_ctx)

    if mutated is None:
        mutated, gap = local_mutate(note_page, req.doubt)
        llm_source   = "local"
        answer       = ""

    can_mutate = llm_source in ("azure", "groq")
    mutated    = fix_latex_delimiters(_fix_tables(mutated))

    # ── ADDITIVE-ONLY GUARD ──────────────────────────────────────────────────
    # If the LLM shrank the page (deleted content), reject the rewrite and
    # instead prepend the new additions above the original content.
    if can_mutate and len(mutated.strip()) < len(note_page.strip()):
        logger.warning(
            "Mutation shrank page from %d → %d chars — falling back to additive prepend",
            len(note_page), len(mutated),
        )
        # Extract the heading from the original to avoid duplication
        import re as _re
        heading_match = _re.match(r'^(##\s+[^\n]+)\n', note_page.strip())
        heading = heading_match.group(1) if heading_match else None
        # Build the addition: intuition block from the gap + answer
        addition_parts = []
        if gap and gap != "Student required additional clarification.":
            addition_parts.append(f"> 💡 **Intuition (re: \"{req.doubt.strip()}\"):** {gap}")
        if answer:
            addition_parts.append(answer)
        addition = "\n\n".join(addition_parts) if addition_parts else (
            f"> 💡 **Clarification:** See below for the original content addressing: \"{req.doubt.strip()}\""
        )
        if heading:
            body = note_page.strip()[len(heading):].strip()
            mutated = f"{heading}\n\n{addition}\n\n{body}"
        else:
            mutated = f"{addition}\n\n{note_page.strip()}"

    if can_mutate and req.notebook_id:
        try:
            updated = update_note_page(req.notebook_id, req.page_idx, mutated)
            if updated:
                full_note = "\n\n".join(get_all_note_pages(req.notebook_id))
                update_notebook_note(req.notebook_id, full_note)
        except Exception as e:
            logger.warning("Page update failed: %s", e)

    _safe, _cat = await check_content_safety(mutated)
    if not _safe:
        logger.warning("Content Safety flagged mutation output: category=%s", _cat)

    if req.notebook_id and mutated:
        try:
            graph = extract_concepts(mutated)
            if graph.get("nodes"):
                top_concept = graph["nodes"][0]["label"]
                update_node_status(top_concept, "partial", _username)
                increment_mutation_count(top_concept, _username)
        except Exception:
            pass

    if can_mutate:
        _record_llm_call(user["id"], llm_source, est_tokens=3000)

    return MutationResponse(
        mutated_paragraph=mutated,
        concept_gap=gap or "Student required additional clarification.",
        answer=fix_latex_delimiters(answer) if answer else (gap or ""),
        page_idx=req.page_idx,
        source=llm_source,
        can_mutate=can_mutate,
    )


# ── Regenerate section ─────────────────────────────────────────────────────────

@router.post("/api/regenerate-section", response_model=RegenerateSectionResponse)
async def regenerate_section(
    req: RegenerateSectionRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks, get_note_page, update_note_page, get_all_note_pages
    from agents.notebook_store import update_notebook_note
    from agents.latex_utils import fix_latex_delimiters
    from pipeline.note_generator import _fix_tables

    user              = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])          # FIX: was missing — allowed unlimited API calls
    nb                = _require_notebook_owner(req.notebook_id, user)
    current_page_text = get_note_page(req.notebook_id, req.page_idx) or ""

    if not current_page_text and nb.get("note"):
        note_pages        = re.split(r'(?m)^(?=## )', nb["note"])
        note_pages        = [p.strip() for p in note_pages if p.strip()]
        if req.page_idx < len(note_pages):
            current_page_text = note_pages[req.page_idx]

    if not current_page_text:
        raise HTTPException(404, "Page not found in notebook")

    heading_match = re.match(r'^#{1,3}\s+(.+)', current_page_text)
    topic         = heading_match.group(1) if heading_match else current_page_text[:80]

    slide_hits    = retrieve_relevant_chunks(req.notebook_id, topic, top_k=8, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(req.notebook_id, topic, top_k=8, source_filter="textbook")
    slide_ctx     = _format_chunks_for_prompt(slide_hits,    10_000)
    textbook_ctx  = _format_chunks_for_prompt(textbook_hits, 10_000)

    custom_direction = (
        f"\nSTUDENT DIRECTION: {req.custom_prompt.strip()}\n"
        f"(Honour the student's direction above when writing this section.)\n"
        if req.custom_prompt and req.custom_prompt.strip() else ""
    )
    regen_prompt = (
        f"You are AuraGraph's note-generation engine. Re-write the following study note section "
        f"**from scratch**, using only the source material below.\n\n"
        f"TOPIC: {topic}\nPROFICIENCY LEVEL: {req.proficiency}\n"
        f"{custom_direction}\n"
        f"SOURCE MATERIAL:\n--- SLIDES ---\n{slide_ctx}\n\n--- TEXTBOOK ---\n{textbook_ctx}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Write a single cohesive section starting with \"## {topic}\"\n"
        f"- Use LaTeX math ($...$ for inline, $$...$$ for display)\n"
        f"- Include key formulas, definitions, and intuition calibrated to {req.proficiency} level\n"
        f"- Do NOT copy the old note — write a fresh, improved version\n"
        f"- Output ONLY the markdown note section (no preamble)"
    )

    llm_source  = "local"
    new_section = ""

    if deps._is_azure_available():
        try:
            new_section = await deps._azure_chat([{"role": "user", "content": regen_prompt}], max_tokens=3000)
            llm_source  = "azure"
        except Exception as e:
            logger.warning("Azure regenerate failed: %s", e)

    if not new_section and deps._is_groq_available():
        try:
            new_section = await deps._groq_chat([{"role": "user", "content": regen_prompt}], max_tokens=3000)
            llm_source  = "groq"
        except Exception as e:
            logger.warning("Groq regenerate failed: %s", e)

    if llm_source in ("azure", "groq"):
        _record_llm_call(user["id"], llm_source, est_tokens=3000)

    if not new_section:
        new_section = current_page_text + "\n\n> *(Regeneration unavailable — AI offline. Original section kept.)*"
        llm_source  = "local"
    else:
        new_section = fix_latex_delimiters(_fix_tables(new_section))
        try:
            update_note_page(req.notebook_id, req.page_idx, new_section)
            full_note = "\n\n".join(get_all_note_pages(req.notebook_id))
            update_notebook_note(req.notebook_id, full_note)
        except Exception as e:
            logger.warning("Failed to persist regenerated section: %s", e)

    return RegenerateSectionResponse(new_section=new_section, page_idx=req.page_idx, source=llm_source)


# ── Sniper exam ────────────────────────────────────────────────────────────────

@router.post("/api/sniper-exam", response_model=SniperExamResponse)
async def sniper_exam(
    req: SniperExamRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks
    from agents.examiner_agent import SNIPER_EXAM_PROMPT

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])     # FIX: was missing
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    # Use weak_concepts from frontend (authoritative source of graph state)
    struggling = (req.weak_concepts or [])[:5]

    if not struggling:
        return SniperExamResponse(questions=[], concepts_tested=[])

    partial: list[str] = []

    concepts_tested = (
        [{"label": l, "status": "struggling"} for l in struggling] +
        [{"label": l, "status": "partial"}    for l in partial]
    )

    nb_ctx = ""
    if req.notebook_id:
        q         = " ".join(struggling + partial)
        sh        = retrieve_relevant_chunks(req.notebook_id, q, top_k=14, source_filter="slides")
        th        = retrieve_relevant_chunks(req.notebook_id, q, top_k=6,  source_filter="textbook")
        sc        = _format_chunks_for_prompt(sh, 5000)
        tc        = _format_chunks_for_prompt(th, 2000)
        nb_ctx    = f"[FROM SLIDES]\n{sc}\n\n[FROM TEXTBOOK]\n{tc}" if sc and tc else (sc or tc)

    def _build_prompt():
        return (
            SNIPER_EXAM_PROMPT
            .replace("{{$struggling_concepts}}", ", ".join(struggling) or "None")
            .replace("{{$partial_concepts}}",    ", ".join(partial)    or "None")
            .replace("{{$notebook_context}}",    nb_ctx or "(no course context available)")
        )

    raw = ""
    logger.info("sniper-exam: struggling=%s partial=%s azure=%s groq=%s",
                struggling, partial, deps._is_azure_available(), deps._is_groq_available())
    if deps._is_azure_available():
        try:
            raw = await deps._azure_chat([{"role": "user", "content": _build_prompt()}], max_tokens=4000)
            logger.info("Azure sniper exam OK, len=%d", len(raw) if raw else 0)
        except Exception as e:
            logger.warning("Azure sniper exam failed: %s — %s", type(e).__name__, e)
    if not raw and deps._is_groq_available():
        try:
            raw = await deps._groq_chat([{"role": "user", "content": _build_prompt()}], max_tokens=2500)
            logger.info("Groq sniper exam OK, len=%d", len(raw) if raw else 0)
        except Exception as e:
            logger.warning("Groq sniper exam failed: %s — %s", type(e).__name__, e)

    questions: list = []
    if raw:
        try:
            clean = re.sub(r"^```[a-z]*\n?", "", raw.strip())
            clean = re.sub(r"\n?```$", "", clean.strip())
            if not clean.lstrip().startswith('['):
                m = re.search(r'\[[\s\S]+\]', clean)
                if m:
                    clean = m.group(0)
            parsed = _parse_llm_json(clean)
            if isinstance(parsed, list):
                questions = parsed
        except Exception as e:
            logger.warning("Sniper exam JSON parse failed: %s", e)

    if not questions:
        for label in (struggling + partial)[:5]:
            questions.append({
                "question":    f"Describe the key aspects of {label}.",
                "options":     {"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"},
                "correct":     "A",
                "explanation": "Backend offline — reconnect for AI-generated questions.",
                "concept":     label,
            })

    return SniperExamResponse(questions=questions, concepts_tested=concepts_tested)

# ── General exam ────────────────────────────────────────────────────────────────────

@router.post("/api/general-exam", response_model=GeneralExamResponse)
async def general_exam(
    req: GeneralExamRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks
    from agents.examiner_agent import GENERAL_EXAM_PROMPT

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    all_concepts = (req.all_concepts or [])[:15]
    if not all_concepts:
        return GeneralExamResponse(questions=[], concepts_tested=[])

    concepts_tested = [{"label": l, "status": "all"} for l in all_concepts]

    nb_ctx = ""
    if req.notebook_id:
        q  = " ".join(all_concepts)
        sh = retrieve_relevant_chunks(req.notebook_id, q, top_k=14, source_filter="slides")
        th = retrieve_relevant_chunks(req.notebook_id, q, top_k=6,  source_filter="textbook")
        sc = _format_chunks_for_prompt(sh, 6000)
        tc = _format_chunks_for_prompt(th, 3000)
        nb_ctx = f"[FROM SLIDES]\n{sc}\n\n[FROM TEXTBOOK]\n{tc}" if sc and tc else (sc or tc)

    def _build_prompt():
        return (
            GENERAL_EXAM_PROMPT
            .replace("{{$all_concepts}}", ", ".join(all_concepts))
            .replace("{{$notebook_context}}", nb_ctx or "(no course context available)")
        )

    raw = ""
    if deps._is_azure_available():
        try:
            raw = await deps._azure_chat([{"role": "user", "content": _build_prompt()}], max_tokens=6000)
        except Exception as e:
            logger.warning("Azure general exam failed: %s", e)
    if not raw and deps._is_groq_available():
        try:
            raw = await deps._groq_chat([{"role": "user", "content": _build_prompt()}], max_tokens=4000)
        except Exception as e:
            logger.warning("Groq general exam failed: %s", e)

    questions: list = []
    if raw:
        try:
            clean = re.sub(r"^```[a-z]*\n?", "", raw.strip())
            clean = re.sub(r"\n?```$", "", clean.strip())
            if not clean.lstrip().startswith('['):
                m = re.search(r'\[[\s\S]+\]', clean)
                if m:
                    clean = m.group(0)
            parsed = _parse_llm_json(clean)
            if isinstance(parsed, list):
                questions = parsed
        except Exception as e:
            logger.warning("General exam JSON parse failed: %s", e)

    if not questions:
        for label in all_concepts[:10]:
            questions.append({
                "question":    f"Describe the key aspects of {label}.",
                "options":     {"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"},
                "correct":     "A",
                "explanation": "Backend offline — reconnect for AI-generated questions.",
                "concept":     label,
            })

    return GeneralExamResponse(questions=questions, concepts_tested=concepts_tested)

# ── Examiner ───────────────────────────────────────────────────────────────────

@router.post("/api/examine", response_model=ExaminerResponse)
async def examine_concept(
    req: ExaminerRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks
    from agents.local_examiner import local_examine
    from agents.latex_utils import fix_latex_delimiters
    from agents.examiner_agent import EXAMINER_PROMPT

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])     # FIX: was missing
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    ci     = (req.custom_instruction or "").strip()
    nb_ctx = ""
    if req.notebook_id:
        sh     = retrieve_relevant_chunks(req.notebook_id, req.concept_name, top_k=12, source_filter="slides")
        th     = retrieve_relevant_chunks(req.notebook_id, req.concept_name, top_k=8,  source_filter="textbook")
        sc     = _format_chunks_for_prompt(sh, 5000)
        tc     = _format_chunks_for_prompt(th, 3000)
        nb_ctx = f"[FROM SLIDES]\n{sc}\n\n[FROM TEXTBOOK]\n{tc}" if sc and tc else (sc or tc)

    if deps.examiner_agent and deps._is_azure_available():
        try:
            q = await deps.examiner_agent.examine(req.concept_name, notebook_context=nb_ctx, custom_instruction=ci)
            return ExaminerResponse(practice_questions=fix_latex_delimiters(q))
        except Exception as e:
            logger.warning("Azure examiner failed: %s", e)

    if deps._is_groq_available():
        try:
            ci_full = f"\n\nCUSTOM FOCUS (follow exactly): {ci}" if ci else ""
            prompt  = (
                EXAMINER_PROMPT
                .replace("{{$concept_name}}", req.concept_name)
                .replace("{{$notebook_context}}", nb_ctx or "(no course context available)")
                .replace("{{$custom_instruction}}", ci_full)
            )
            q = await deps._groq_chat([{"role": "user", "content": prompt}], max_tokens=4000)
            return ExaminerResponse(practice_questions=fix_latex_delimiters(q))
        except Exception as e:
            logger.warning("Groq examiner failed: %s", e)

    return ExaminerResponse(practice_questions=fix_latex_delimiters(local_examine(req.concept_name)))


# ── Concept practice ───────────────────────────────────────────────────────────

@router.post("/api/concept-practice", response_model=ConceptPracticeResponse)
async def concept_practice_endpoint(
    req: ConceptPracticeRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks
    from agents.examiner_agent import CONCEPT_PRACTICE_PROMPT

    user  = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])     # FIX: was missing
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    level  = req.level.lower().strip()
    if level not in ("struggling", "partial", "mastered"):
        level = "partial"
    ci     = (req.custom_instruction or "").strip()
    nb_ctx = ""

    if req.notebook_id:
        sh     = retrieve_relevant_chunks(req.notebook_id, req.concept_name, top_k=12, source_filter="slides")
        th     = retrieve_relevant_chunks(req.notebook_id, req.concept_name, top_k=6,  source_filter="textbook")
        sc     = _format_chunks_for_prompt(sh, 5000)
        tc     = _format_chunks_for_prompt(th, 2500)
        nb_ctx = f"[FROM SLIDES]\n{sc}\n\n[FROM TEXTBOOK]\n{tc}" if sc and tc else (sc or tc)

    ci_full = f"\n\nCUSTOM FOCUS (follow exactly): {ci}" if ci else ""

    def _build_prompt():
        return (
            CONCEPT_PRACTICE_PROMPT
            .replace("{{$concept_name}}", req.concept_name)
            .replace("{{$level}}",        level)
            .replace("{{$notebook_context}}", nb_ctx or "(no course context available)")
            .replace("{{$custom_instruction}}", ci_full)
        )

    raw: str | None = None
    logger.info("concept-practice: examiner=%s azure=%s groq=%s concept=%s level=%s",
                bool(deps.examiner_agent), deps._is_azure_available(),
                deps._is_groq_available(), req.concept_name, level)
    if deps.examiner_agent and deps._is_azure_available():
        try:
            raw = await deps.examiner_agent.concept_practice(
                req.concept_name, level, notebook_context=nb_ctx, custom_instruction=ci
            )
            logger.info("Azure concept-practice OK, len=%d", len(raw) if raw else 0)
        except Exception as e:
            logger.warning("Azure concept-practice failed: %s — %s", type(e).__name__, e)

    if raw is None and deps._is_groq_available():
        try:
            raw = await deps._groq_chat([{"role": "user", "content": _build_prompt()}], max_tokens=2000)
            logger.info("Groq concept-practice OK, len=%d", len(raw) if raw else 0)
        except Exception as e:
            logger.warning("Groq concept-practice failed: %s — %s", type(e).__name__, e)

    if raw:
        stripped = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        stripped = re.sub(r'\s*```$', '', stripped.strip())
        if not stripped.lstrip().startswith('['):
            m = re.search(r'\[[\s\S]+\]', stripped)
            if m:
                stripped = m.group(0)
        parsed = _parse_llm_json(stripped)
        if isinstance(parsed, list) and parsed:
            return ConceptPracticeResponse(questions=parsed)

    return ConceptPracticeResponse(questions=[{
        "question": f"Which of the following best describes '{req.concept_name}'?",
        "options": {"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"},
        "correct": "A",
        "explanation": "Backend offline — reconnect for AI-generated questions.",
    }])
