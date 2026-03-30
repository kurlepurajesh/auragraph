"""routers/learning.py — doubt, mutate, regenerate, examine, sniper-exam, concept-practice."""
from __future__ import annotations

import json as _json
import logging
import re
from difflib import SequenceMatcher
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
    ConceptExamRequest, ConceptExamResponse,
    QuizRunCompleteRequest, QuizRunCompleteResponse, QuizRunsResponse,
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


def _merge_student_contexts(*parts: str) -> str:
    merged = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return "\n".join(merged)


async def _build_student_context(user_id: str, proficiency: str = "") -> str:
    """Build a merged learner context from behaviour + persisted education profile."""
    import asyncio as _aio
    from agents.behaviour_store import get_personalisation_context
    from agents.auth_utils import get_user_profile, profile_to_student_context

    def _load() -> str:
        try:
            beh_ctx = get_personalisation_context(user_id)
        except Exception:
            beh_ctx = ""
        try:
            profile = get_user_profile(user_id)
            edu_ctx = profile_to_student_context(profile, proficiency=proficiency)
        except Exception:
            edu_ctx = ""
        return _merge_student_contexts(beh_ctx, edu_ctx)

    return await _aio.to_thread(_load)


def _append_student_context(base_context: str, student_context: str) -> str:
    if not student_context:
        return base_context
    return (
        (base_context or "(no course context available)")
        + "\n\nSTUDENT PROFILE CONTEXT (calibration only; do not mention unless asked):\n"
        + student_context
    )


def _feedback_guidance(tag: str) -> str:
    """Fetch compact prompt guidance derived from tagged user feedback."""
    try:
        from agents.notebook_store import get_feedback_prompt_guidance
        return get_feedback_prompt_guidance(tag)
    except Exception as exc:
        logger.debug("feedback guidance unavailable for %s: %s", tag, exc)
        return ""


def _norm_q(text: str) -> str:
    s = (text or "").lower()
    s = re.sub(r"\$+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _recent_quiz_questions(nb_id: str | None, limit_runs: int = 25) -> list[str]:
    if not nb_id:
        return []
    try:
        from agents.notebook_store import list_quiz_runs
        runs = list_quiz_runs(nb_id, limit=limit_runs)
    except Exception:
        return []

    out: list[str] = []
    for run in runs:
        for q in (run.get("questions") or []):
            if isinstance(q, dict):
                t = str(q.get("question") or "").strip()
                if t:
                    out.append(t)
    return out


def _is_near_duplicate(question_text: str, seen: list[str], seen_norm: set[str]) -> bool:
    norm = _norm_q(question_text)
    if not norm:
        return True
    if norm in seen_norm:
        return True
    for prev in seen:
        pnorm = _norm_q(prev)
        if not pnorm:
            continue
        # High threshold: block near-clones while allowing numeric-value variants.
        if SequenceMatcher(None, norm, pnorm).ratio() >= 0.94:
            return True
    return False


def _sanitize_mcq(q: dict, concept_fallback: str) -> dict:
    question = str(q.get("question") or "").strip()
    options = q.get("options") or {}
    if not isinstance(options, dict):
        options = {}
    clean_options = {
        "A": str(options.get("A") or "Option A").strip() or "Option A",
        "B": str(options.get("B") or "Option B").strip() or "Option B",
        "C": str(options.get("C") or "Option C").strip() or "Option C",
        "D": str(options.get("D") or "Option D").strip() or "Option D",
    }
    correct = str(q.get("correct") or "A").strip().upper()
    if correct not in {"A", "B", "C", "D"}:
        correct = "A"
    explanation = str(q.get("explanation") or "").strip() or "Reasoning is based on the notebook context."
    concept = str(q.get("concept") or concept_fallback or "").strip() or concept_fallback
    return {
        "question": question,
        "options": clean_options,
        "correct": correct,
        "explanation": explanation,
        "concept": concept,
    }


def _fallback_quiz_question(concept: str, idx: int) -> dict:
    c = concept or "this concept"
    n1 = 2 + (idx % 7)
    n2 = 5 + ((idx * 3) % 11)
    mode = idx % 4
    if mode == 0:
        return {
            "question": f"Which statement best captures the core idea of {c} in this notebook context?",
            "options": {
                "A": f"A precise definition with necessary conditions of {c}",
                "B": "A loosely related intuition with missing conditions",
                "C": "An unrelated theorem from another topic",
                "D": "A computational shortcut that ignores assumptions",
            },
            "correct": "A",
            "explanation": f"The strongest answer states the full definition/conditions of {c}; the others omit key assumptions or drift off-topic.",
            "concept": c,
        }
    if mode == 1:
        return {
            "question": f"A worked example scales two inputs by {n1} and {n2}. Which option correctly applies the notebook formula for {c}?",
            "options": {
                "A": "Apply the same formula with substituted values and preserve units",
                "B": "Average the inputs first and apply a different relation",
                "C": "Square both inputs before any substitution",
                "D": "Use sign changes without formula substitution",
            },
            "correct": "A",
            "explanation": "Numerical questions should keep the original formula structure and substitute values consistently; other options alter the method.",
            "concept": c,
        }
    if mode == 2:
        return {
            "question": f"For {c}, what is the most likely consequence if a key assumption is violated in a proof or derivation step?",
            "options": {
                "A": "The claimed result may fail because the derivation no longer holds",
                "B": "The result remains exact regardless of assumptions",
                "C": "Only notation changes, not validity",
                "D": "The conclusion becomes stronger automatically",
            },
            "correct": "A",
            "explanation": "Logical validity depends on assumptions. If an assumption breaks, the derivation can break too.",
            "concept": c,
        }
    return {
        "question": f"A student got this {c} question wrong. Which correction best fixes the common mistake?",
        "options": {
            "A": "Re-check assumptions, then apply the exact notebook relation step-by-step",
            "B": "Memorize only the final result and skip intermediate logic",
            "C": "Replace all symbols with new ones and keep the same mistake",
            "D": "Ignore boundary conditions in every case",
        },
        "correct": "A",
        "explanation": "Most errors come from skipped assumptions or misapplied formulas; disciplined step-by-step correction fixes them.",
        "concept": c,
    }


def _dedupe_and_fill_questions(
    parsed: list,
    recent_questions: list[str],
    concepts: list[str],
    target_count: int,
) -> list[dict]:
    selected: list[dict] = []
    seen_texts: list[str] = list(recent_questions)
    seen_norm: set[str] = {_norm_q(t) for t in recent_questions if _norm_q(t)}

    for item in (parsed or []):
        if not isinstance(item, dict):
            continue
        concept = str(item.get("concept") or "").strip() or (concepts[0] if concepts else "")
        clean = _sanitize_mcq(item, concept)
        q_text = clean.get("question", "")
        if not q_text or _is_near_duplicate(q_text, seen_texts, seen_norm):
            continue
        selected.append(clean)
        seen_texts.append(q_text)
        seen_norm.add(_norm_q(q_text))
        if len(selected) >= target_count:
            return selected

    if not concepts:
        concepts = ["core concept"]
    for i in range(target_count * 3):
        if len(selected) >= target_count:
            break
        concept = concepts[i % len(concepts)]
        candidate = _fallback_quiz_question(concept, i)
        q_text = candidate["question"]
        if _is_near_duplicate(q_text, seen_texts, seen_norm):
            continue
        selected.append(candidate)
        seen_texts.append(q_text)
        seen_norm.add(_norm_q(q_text))

    # If strict near-duplicate filtering was too aggressive, do a second pass
    # with exact-normalized dedupe only so we still return the required count.
    for i in range(target_count * 8, target_count * 20):
        if len(selected) >= target_count:
            break
        concept = concepts[i % len(concepts)]
        candidate = _fallback_quiz_question(concept, i)
        q_text = candidate["question"]
        norm = _norm_q(q_text)
        if not norm or norm in seen_norm:
            continue
        selected.append(candidate)
        seen_texts.append(q_text)
        seen_norm.add(norm)

    return selected[:target_count]


def _uniqueness_instruction(recent_questions: list[str], quiz_kind: str, target_count: int) -> str:
    recent = [q.strip() for q in recent_questions if q and q.strip()][:12]
    lines = [
        "DIVERSITY & NON-REPEAT RULES (strict):",
        f"- Generate exactly {target_count} NEW questions.",
        "- Do not repeat or closely paraphrase any prior question stem from previous quizzes.",
        "- Keep definition-only questions to at most 1.",
        "- Include at least 2 numeric/application questions with changed values.",
        "- Include at least 2 logical/what-if/error-analysis questions.",
        "- Include at least 1 comparison/distinction question.",
    ]
    if quiz_kind == "sniper":
        lines.append("- Prioritize weak concepts, but still vary difficulty and format.")
    if recent:
        lines.append("- Avoid these recent stems:")
        for i, q in enumerate(recent, 1):
            lines.append(f"  {i}. {q[:180]}")
    return "\n".join(lines)


# ── Doubt answering ────────────────────────────────────────────────────────────

@router.post("/api/doubt", response_model=DoubtResponse)
async def answer_doubt(
    req: DoubtRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import retrieve_relevant_chunks, get_note_page
    from agents.verifier_agent import parse_verification_response
    from agents.content_safety import check_output, check_input, sanitise_input, strip_error_exposure_language
    from agents.latex_utils import fix_latex_delimiters
    from agents.behaviour_store import track_doubt

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    _require_notebook_owner(req.notebook_id, user)

    # ── Screen student input before touching any LLM ──────────────────────────
    _input_safe, _input_cat = await check_input(req.doubt)
    if not _input_safe:
        from fastapi import HTTPException
        raise HTTPException(400, f"Your question contains content that cannot be processed ({_input_cat}). Please rephrase.")
    # Strip profanity — preserve academic intent, never echo curse words
    doubt_clean, _was_sanitised = sanitise_input(req.doubt)
    if _was_sanitised:
        logger.info("Input sanitised for user %s", user["id"])

    # Track doubt in background, then build merged learner context for prompt calibration.
    import asyncio as _aio

    def _track_only():
        try:
            track_doubt(
                user_id=user["id"],
                notebook_id=req.notebook_id,
                topic=" ".join(doubt_clean.split()[:6]),
                question=doubt_clean,
                page_idx=getattr(req, "page_idx", 0) or 0,
            )
        except Exception:
            pass

    _aio.ensure_future(_aio.to_thread(_track_only))
    student_ctx = await _build_student_context(user["id"])
    doubt_feedback = _feedback_guidance("doubts")
    merged_student_ctx = _merge_student_contexts(student_ctx, doubt_feedback)

    slide_hits    = retrieve_relevant_chunks(req.notebook_id, doubt_clean, top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(req.notebook_id, doubt_clean, top_k=6, source_filter="textbook")
    slide_ctx    = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_ctx = _format_chunks_for_prompt(textbook_hits, 8_000)
    note_page    = get_note_page(req.notebook_id, req.page_idx) or ""

    raw_text: str | None = None
    source = "local"

    if deps._is_azure_available():
        try:
            raw_text = str(await deps.fusion_agent.answer_doubt(
                doubt=doubt_clean, slide_context=slide_ctx,
                textbook_context=textbook_ctx, note_page=note_page,
                student_context=merged_student_ctx,
            ))
            source = "azure"
        except Exception as e:
            logger.warning("Azure doubt failed: %s", e)

    if raw_text is None and deps._is_groq_available():
        try:
            raw_text = await deps._groq_doubt(doubt_clean, slide_ctx, textbook_ctx, note_page, student_context=merged_student_ctx)
            source   = "groq"
        except Exception as e:
            logger.warning("Groq doubt failed: %s", e)

    if raw_text is not None:
        vr = parse_verification_response(raw_text)
        _safe, _cat = await check_output(vr.answer)
        if not _safe:
            logger.warning("Content Safety blocked doubt answer: category=%s", _cat)
            _record_llm_call(user["id"], source, est_tokens=1500)
            return DoubtResponse(
                answer="I'm unable to provide a response to this question as the generated answer was flagged by our content filter. Please try rephrasing your question.",
                source=source,
            )
        from agents.content_safety import strip_error_exposure_language
        clean_answer = strip_error_exposure_language(fix_latex_delimiters(vr.answer or ""))
        _record_llm_call(user["id"], source, est_tokens=1500)
        return DoubtResponse(
            answer=clean_answer,
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
    from agents.content_safety import check_output, check_input, sanitise_input, strip_error_exposure_language
    from agents.local_mutation import local_mutate, _build_analogy_hint
    from agents.concept_extractor import extract_concepts
    from agents.latex_utils import fix_latex_delimiters
    from pipeline.note_generator import _fix_tables

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    _require_notebook_owner(req.notebook_id, user)
    _username = user["id"]

    # Screen + sanitise student input before mutation
    _in_safe_mut, _in_cat_mut = await check_input(req.doubt or "")
    if not _in_safe_mut:
        raise HTTPException(400, f"Your doubt contains content that cannot be processed ({_in_cat_mut}).")
    _doubt_clean_mut, _ = sanitise_input(req.doubt or "")

    # Track mutation doubt in background (non-blocking)
    import asyncio as _aio2
    async def _bg_track_mut():
        try:
            from agents.behaviour_store import track_doubt as _td
            await _aio2.to_thread(_td, _username, req.notebook_id,
                " ".join(_doubt_clean_mut.split()[:6]), _doubt_clean_mut,
                getattr(req, "page_idx", 0) or 0)
        except Exception:
            pass
    _aio2.ensure_future(_bg_track_mut())

    note_page = get_note_page(req.notebook_id, req.page_idx)
    if note_page is None:
        note_page = req.original_paragraph or ""

    query         = _doubt_clean_mut + " " + note_page[:200]
    slide_hits    = retrieve_relevant_chunks(req.notebook_id, query, top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(req.notebook_id, query, top_k=6, source_filter="textbook")
    slide_ctx     = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_ctx  = _format_chunks_for_prompt(textbook_hits, 8_000)

    student_ctx = await _build_student_context(user["id"])
    doubt_for_llm = _doubt_clean_mut
    if student_ctx:
        doubt_for_llm += (
            "\n\nStudent Profile Context (calibration only; do not mention unless asked):\n"
            + student_ctx
        )
    mutation_feedback = _feedback_guidance("mutation")
    if mutation_feedback:
        doubt_for_llm += "\n\n" + mutation_feedback

    mutated, gap, answer, llm_source = await deps._llm_mutate(note_page, doubt_for_llm, slide_ctx, textbook_ctx)

    if mutated is None:
        mutated, gap = local_mutate(note_page, _doubt_clean_mut)
        llm_source   = "local"
        answer       = ""

    can_mutate = llm_source in ("azure", "groq")

    def _inject_addition_preserving_page(original_page: str, addition_md: str, doubt_text: str) -> str:
        """
        Insert clarification near the most relevant paragraph without changing existing words.
        Fallback: append at the bottom of the page.
        """
        page = original_page if isinstance(original_page, str) else ""
        if not page:
            return addition_md

        parts = re.split(r'(\n\s*\n)', page)
        paragraphs = [parts[i] for i in range(0, len(parts), 2)]
        separators = [parts[i] for i in range(1, len(parts), 2)]

        if not paragraphs:
            return page + "\n\n" + addition_md

        stop = {
            "what", "why", "how", "when", "where", "which", "whose", "whom",
            "does", "did", "that", "this", "these", "those", "with", "from",
            "into", "about", "your", "you", "please", "explain", "tell",
        }
        q_words = [w for w in re.findall(r"[a-zA-Z]{3,}", (doubt_text or "").lower()) if w not in stop]
        if not q_words:
            return page.rstrip() + "\n\n" + addition_md

        best_idx = -1
        best_score = 0
        for i, para in enumerate(paragraphs):
            p = para.strip()
            if not p:
                continue
            # Avoid anchoring to heading-only lines.
            if re.match(r'^#{1,6}\s+', p):
                continue
            p_lower = p.lower()
            score = 0
            for w in q_words:
                if len(w) < 4:
                    continue
                if w in p_lower:
                    score += p_lower.count(w)
            if score > best_score:
                best_score = score
                best_idx = i

        # If no reliable match, append clarification at the end (requested fallback).
        if best_idx < 0 or best_score <= 0:
            return page.rstrip() + "\n\n" + addition_md

        rebuilt = []
        for i, para in enumerate(paragraphs):
            rebuilt.append(para)
            if i == best_idx:
                rebuilt.append("\n\n" + addition_md)
            if i < len(separators):
                rebuilt.append(separators[i])
        return "".join(rebuilt)

    # Strict additive mutation policy:
    # keep the current page exactly as-is and only append relevant clarification.
    answer_clean = strip_error_exposure_language(fix_latex_delimiters(answer or "")).strip()
    if answer_clean:
        addition = answer_clean
    else:
        local_hint = _build_analogy_hint(_doubt_clean_mut)
        addition = f"> 💡 **Clarification:** {local_hint}"

    addition = fix_latex_delimiters(_fix_tables(addition))
    mutated = _inject_addition_preserving_page(note_page or "", addition, _doubt_clean_mut)

    if can_mutate and req.notebook_id:
        try:
            updated = update_note_page(req.notebook_id, req.page_idx, mutated)
            if updated:
                full_note = "\n\n".join(get_all_note_pages(req.notebook_id))
                update_notebook_note(req.notebook_id, full_note)
        except Exception as e:
            logger.warning("Page update failed: %s", e)

    from agents.content_safety import check_output as _cs_out
    _safe, _cat = await _cs_out(mutated)
    if not _safe:
        logger.warning("Content Safety blocked mutation: category=%s", _cat)
        return MutationResponse(
            mutated_paragraph=req.original_paragraph or "",
            concept_gap="Content moderation: the rewritten note was blocked. The original is preserved.",
            can_mutate=False,
        )

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

    safe_mutated = mutated or ""
    safe_answer  = answer_clean
    # Final guard: never return an empty mutated_paragraph — fall back to original
    if not safe_mutated.strip():
        safe_mutated = req.original_paragraph or note_page or ""
        logger.warning("mutation: safe_mutated was empty after processing — falling back to original page")

    return MutationResponse(
        mutated_paragraph=safe_mutated,
        concept_gap=gap or "Clarification added to strengthen this concept.",
        answer=safe_answer,
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

    _regen_student_ctx = await _build_student_context(user["id"], proficiency=req.proficiency)

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
        f"- Output ONLY the markdown note section (no preamble)\n\n"
        + (_regen_student_ctx + "\n" if _regen_student_ctx else "")
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
    from agents.knowledge_store import build_quiz_context
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
    recent_questions = _recent_quiz_questions(req.notebook_id)
    uniq_instr = _uniqueness_instruction(recent_questions, quiz_kind="sniper", target_count=5)

    nb_ctx = build_quiz_context(req.notebook_id, " ".join(struggling + partial)) if req.notebook_id else ""
    student_ctx = await _build_student_context(user["id"])
    quiz_ctx = _append_student_context(nb_ctx or "(no course context available)", student_ctx)
    quiz_feedback = _feedback_guidance("questions")
    if quiz_feedback:
        quiz_ctx += "\n\n" + quiz_feedback

    def _build_prompt():
        return (
            SNIPER_EXAM_PROMPT
            .replace("{{$struggling_concepts}}", ", ".join(struggling) or "None")
            .replace("{{$partial_concepts}}",    ", ".join(partial)    or "None")
            .replace("{{$notebook_context}}",    quiz_ctx)
            + "\n\n" + uniq_instr
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

    concepts_for_fill = (struggling + partial) or ["core concept"]
    questions = _dedupe_and_fill_questions(
        parsed=questions,
        recent_questions=recent_questions,
        concepts=concepts_for_fill,
        target_count=5,
    )

    return SniperExamResponse(questions=questions, concepts_tested=concepts_tested)

# ── General exam ────────────────────────────────────────────────────────────────────

@router.post("/api/general-exam", response_model=GeneralExamResponse)
async def general_exam(
    req: GeneralExamRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import build_quiz_context
    from agents.examiner_agent import GENERAL_EXAM_PROMPT

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    all_concepts = (req.all_concepts or [])[:15]
    if not all_concepts:
        return GeneralExamResponse(questions=[], concepts_tested=[])

    concepts_tested = [{"label": l, "status": "all"} for l in all_concepts]
    recent_questions = _recent_quiz_questions(req.notebook_id)
    uniq_instr = _uniqueness_instruction(recent_questions, quiz_kind="general", target_count=10)

    nb_ctx = build_quiz_context(req.notebook_id, " ".join(all_concepts)) if req.notebook_id else ""
    student_ctx = await _build_student_context(user["id"])
    quiz_ctx = _append_student_context(nb_ctx or "(no course context available)", student_ctx)
    quiz_feedback = _feedback_guidance("questions")
    if quiz_feedback:
        quiz_ctx += "\n\n" + quiz_feedback

    def _build_prompt():
        return (
            GENERAL_EXAM_PROMPT
            .replace("{{$all_concepts}}", ", ".join(all_concepts))
            .replace("{{$notebook_context}}", quiz_ctx)
            + "\n\n" + uniq_instr
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

    questions = _dedupe_and_fill_questions(
        parsed=questions,
        recent_questions=recent_questions,
        concepts=all_concepts,
        target_count=10,
    )

    return GeneralExamResponse(questions=questions, concepts_tested=concepts_tested)


@router.post("/api/concept-exam", response_model=ConceptExamResponse)
async def concept_exam(
    req: ConceptExamRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import build_quiz_context
    from agents.examiner_agent import CONCEPT_EXAM_PROMPT

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    concept_name = (req.concept_name or "").strip()
    if not concept_name:
        return ConceptExamResponse(questions=[], concepts_tested=[])

    concepts_tested = [{"label": concept_name, "status": "focused"}]
    recent_questions = _recent_quiz_questions(req.notebook_id)
    uniq_instr = _uniqueness_instruction(recent_questions, quiz_kind="concept", target_count=5)

    nb_ctx = build_quiz_context(req.notebook_id, concept_name) if req.notebook_id else ""
    student_ctx = await _build_student_context(user["id"])
    quiz_ctx = _append_student_context(nb_ctx or "(no course context available)", student_ctx)
    quiz_feedback = _feedback_guidance("questions")
    if quiz_feedback:
        quiz_ctx += "\n\n" + quiz_feedback

    def _build_prompt():
        return (
            CONCEPT_EXAM_PROMPT
            .replace("{{$concept_name}}", concept_name)
            .replace("{{$notebook_context}}", quiz_ctx)
            + "\n\n" + uniq_instr
        )

    raw = ""
    if deps._is_azure_available():
        try:
            raw = await deps._azure_chat([{"role": "user", "content": _build_prompt()}], max_tokens=3500)
        except Exception as e:
            logger.warning("Azure concept exam failed: %s", e)
    if not raw and deps._is_groq_available():
        try:
            raw = await deps._groq_chat([{"role": "user", "content": _build_prompt()}], max_tokens=2500)
        except Exception as e:
            logger.warning("Groq concept exam failed: %s", e)

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
            logger.warning("Concept exam JSON parse failed: %s", e)

    questions = _dedupe_and_fill_questions(
        parsed=questions,
        recent_questions=recent_questions,
        concepts=[concept_name],
        target_count=5,
    )

    return ConceptExamResponse(questions=questions, concepts_tested=concepts_tested)


@router.post("/api/notebooks/{nb_id}/quizzes/complete", response_model=QuizRunCompleteResponse)
async def complete_quiz_attempt(
    nb_id: str,
    req: QuizRunCompleteRequest,
    authorization: Optional[str] = Header(None),
):
    """Persist one completed quiz attempt for notebook review/history."""
    from agents.notebook_store import complete_quiz_run

    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)

    payload = req.model_dump()
    run_id = complete_quiz_run(nb_id, payload)
    return QuizRunCompleteResponse(ok=True, run_id=run_id)


@router.get("/api/notebooks/{nb_id}/quizzes", response_model=QuizRunsResponse)
async def get_quiz_history(
    nb_id: str,
    authorization: Optional[str] = Header(None),
    limit: int = 100,
):
    """Return quiz history for a notebook, newest first."""
    from agents.notebook_store import list_quiz_runs

    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)

    quizzes = list_quiz_runs(nb_id, limit=limit)
    return QuizRunsResponse(quizzes=quizzes, total=len(quizzes))

# ── Examiner ───────────────────────────────────────────────────────────────────

@router.post("/api/examine", response_model=ExaminerResponse)
async def examine_concept(
    req: ExaminerRequest,
    authorization: Optional[str] = Header(None),
):
    from agents.knowledge_store import build_quiz_context
    from agents.local_examiner import local_examine
    from agents.latex_utils import fix_latex_delimiters
    from agents.examiner_agent import EXAMINER_PROMPT

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])     # FIX: was missing
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    ci     = (req.custom_instruction or "").strip()
    nb_ctx = build_quiz_context(req.notebook_id, req.concept_name) if req.notebook_id else ""
    student_ctx = await _build_student_context(user["id"])
    quiz_ctx = _append_student_context(nb_ctx or "(no course context available)", student_ctx)
    quiz_feedback = _feedback_guidance("questions")
    if quiz_feedback:
        ci = (ci + "\n\n" + quiz_feedback).strip()

    if deps.examiner_agent and deps._is_azure_available():
        try:
            q = await deps.examiner_agent.examine(req.concept_name, notebook_context=quiz_ctx, custom_instruction=ci)
            return ExaminerResponse(practice_questions=fix_latex_delimiters(q))
        except Exception as e:
            logger.warning("Azure examiner failed: %s", e)

    if deps._is_groq_available():
        try:
            ci_full = f"\n\nCUSTOM FOCUS (follow exactly): {ci}" if ci else ""
            prompt  = (
                EXAMINER_PROMPT
                .replace("{{$concept_name}}", req.concept_name)
                .replace("{{$notebook_context}}", quiz_ctx)
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
    from agents.knowledge_store import build_quiz_context
    from agents.examiner_agent import CONCEPT_PRACTICE_PROMPT

    user  = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])     # FIX: was missing
    if req.notebook_id:
        _require_notebook_owner(req.notebook_id, user)

    level  = req.level.lower().strip()
    if level not in ("struggling", "partial", "mastered"):
        level = "partial"
    ci     = (req.custom_instruction or "").strip()
    nb_ctx = build_quiz_context(req.notebook_id, req.concept_name) if req.notebook_id else ""
    student_ctx = await _build_student_context(user["id"])
    quiz_ctx = _append_student_context(nb_ctx or "(no course context available)", student_ctx)
    quiz_feedback = _feedback_guidance("questions")
    if quiz_feedback:
        ci = (ci + "\n\n" + quiz_feedback).strip()

    ci_full = f"\n\nCUSTOM FOCUS (follow exactly): {ci}" if ci else ""

    def _build_prompt():
        return (
            CONCEPT_PRACTICE_PROMPT
            .replace("{{$concept_name}}", req.concept_name)
            .replace("{{$level}}",        level)
            .replace("{{$notebook_context}}", quiz_ctx)
            .replace("{{$custom_instruction}}", ci_full)
        )

    raw: str | None = None
    logger.info("concept-practice: examiner=%s azure=%s groq=%s concept=%s level=%s",
                bool(deps.examiner_agent), deps._is_azure_available(),
                deps._is_groq_available(), req.concept_name, level)
    if deps.examiner_agent and deps._is_azure_available():
        try:
            raw = await deps.examiner_agent.concept_practice(
                req.concept_name, level, notebook_context=quiz_ctx, custom_instruction=ci
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


# ── Behaviour tracking endpoints ──────────────────────────────────────────────

from pydantic import BaseModel as _BM

class TrackQuizAnswerRequest(_BM):
    notebook_id: str
    concept: str
    question: str
    correct: bool

class TrackHighlightRequest(_BM):
    notebook_id: str
    text: str
    page_idx: int = 0


class AuraStateRequest(_BM):
    xp: int = 0
    quizzesCompleted: int = 0
    correctAnswers: int = 0
    totalAnswers: int = 0
    doubtsAsked: int = 0
    highlightsAdded: int = 0
    activeTheme: str = "default"


@router.get("/api/aura")
async def get_aura_state(
    authorization: Optional[str] = Header(None),
):
    """Returns the current user's Aura XP profile from server storage."""
    from agents.aura_store import get_aura
    user = get_current_user(authorization)
    return {"aura": get_aura(user["id"])}


@router.put("/api/aura")
async def save_aura_state(
    req: AuraStateRequest,
    authorization: Optional[str] = Header(None),
):
    """Upserts the current user's Aura XP profile to server storage."""
    from agents.aura_store import save_aura
    user = get_current_user(authorization)
    saved = save_aura(user["id"], req.model_dump())
    return {"ok": True, "aura": saved}


@router.post("/api/behaviour/track-quiz")
async def track_quiz_answer_endpoint(
    req: TrackQuizAnswerRequest,
    authorization: Optional[str] = Header(None),
):
    """Called from frontend after each quiz answer to track learning behaviour."""
    from agents.behaviour_store import track_quiz_answer
    user = get_current_user(authorization)
    try:
        track_quiz_answer(
            user_id=user["id"],
            notebook_id=req.notebook_id,
            concept=req.concept,
            question=req.question,
            correct=req.correct,
        )
    except Exception as e:
        logger.warning("track_quiz_answer failed: %s", e)
    return {"ok": True}


@router.post("/api/behaviour/track-highlight")
async def track_highlight_endpoint(
    req: TrackHighlightRequest,
    authorization: Optional[str] = Header(None),
):
    """Called from frontend when a highlight annotation is added."""
    from agents.behaviour_store import track_highlight
    user = get_current_user(authorization)
    try:
        track_highlight(
            user_id=user["id"],
            notebook_id=req.notebook_id,
            text=req.text,
            page_idx=req.page_idx,
        )
    except Exception as e:
        logger.warning("track_highlight failed: %s", e)
    return {"ok": True}


@router.get("/api/behaviour/profile")
async def get_behaviour_profile(
    authorization: Optional[str] = Header(None),
):
    """Returns the derived personalisation profile for the current user."""
    from agents.behaviour_store import get_profile
    user = get_current_user(authorization)
    try:
        profile = get_profile(user["id"])
        return {"profile": profile}
    except Exception as e:
        logger.warning("get_behaviour_profile failed: %s", e)
        return {"profile": {}}
