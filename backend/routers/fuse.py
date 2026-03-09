"""routers/fuse.py — file upload, SSE streaming note generation, legacy /api/fuse."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Optional, List

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import deps
from deps import (
    get_current_user, _require_notebook_owner,
    _is_azure_available, _is_groq_available,
    _check_llm_rate_limit, _record_llm_call,
    _verify_note, _inject_figures_into_sections, _match_image_to_topic,
    _note_to_pages, _format_chunks_for_prompt,
    MAX_TOTAL_UPLOAD_BYTES, PIPELINE_TIMEOUT_S,
    _PROMPT_SLIDES_BUDGET, _PROMPT_TEXTBOOK_BUDGET,
)
from schemas import FusionResponse, FusionRequest

logger = logging.getLogger("auragraph")
router = APIRouter(tags=["fuse"])

# ── File type validation ───────────────────────────────────────────────────────
_ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp",
})

def _validate_upload(upload: UploadFile) -> None:
    """Reject any file whose extension is not in the allow-list."""
    fname = (upload.filename or "").lower()
    if not any(fname.endswith(ext) for ext in _ALLOWED_EXTENSIONS):
        raise HTTPException(
            415,
            f"Unsupported file type: '{upload.filename}'. "
            f"Allowed types: PDF and image files (PNG, JPG, WEBP, TIFF, BMP)."
        )


def _renumber_pages(text: str, offset: int) -> tuple[str, int]:
    """
    Renumber every '--- Page N ---' and '--- Slide N ---' marker in *text* so
    that page/slide numbers are globally unique across multiple uploaded files.

    Without this, every PDF resets to '--- Page 1 ---' and every PPTX resets
    to '--- Slide 1 ---'. The bipartite safety union in slide_analyzer.py then
    compares source pages {1,2,3,4} against LLM-covered pages {1,2,3,4} —
    collision hides the fact that 14 distinct pages exist across 4 files, and
    nothing is ever rescued.

    Returns (renumbered_text, number_of_pages_found_in_this_file).
    """
    max_local = 0

    def _replace(m: re.Match) -> str:
        nonlocal max_local
        prefix = m.group(1)   # "Page" or "Slide"
        n = int(m.group(2))
        if n > max_local:
            max_local = n
        return f"--- {prefix} {offset + n} ---"

    new_text = re.sub(r'---\s*(Page|Slide)\s+(\d+)\s*---', _replace, text)
    return new_text, max_local




@router.post("/api/upload-fuse-multi", response_model=FusionResponse)
async def upload_fuse_multi(
    slides_pdfs:   List[UploadFile] = File(...),
    textbook_pdfs: Optional[List[UploadFile]] = File(default=None),
    proficiency:   str = Form("Practitioner"),
    notebook_id:   str = Form(""),
    authorization: Optional[str] = Header(None),
):
    """Full 8-step semantic pipeline: extract → chunk → embed → analyse → retrieve → generate → verify → persist."""
    from agents.pdf_utils import extract_text_from_file, chunk_text
    from agents.knowledge_store import store_source_chunks, store_note_pages
    from agents.notebook_store import update_notebook_note
    from agents.local_summarizer import generate_local_note
    from agents.slide_images import extract_images_from_file, save_images
    from agents.image_ocr import describe_slide_image, is_image_file
    from agents.latex_utils import fix_latex_delimiters
    from pipeline.chunker import chunk_textbook
    from pipeline.embedder import Embedder
    from pipeline.vector_db import VectorDB
    from pipeline.slide_analyzer import analyse_slides
    from pipeline.topic_retriever import TopicRetriever
    from pipeline.note_generator import run_generation_pipeline, _fix_tables

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    if notebook_id:
        _require_notebook_owner(notebook_id, user)

    all_slides_text, all_textbook_text = "", ""
    all_slide_images, all_textbook_images, textbook_figures_items = [], [], []
    extraction_errors: list[str] = []
    _total_bytes = 0
    _global_page_offset = 0   # Global page counter across all uploaded slide files

    for upload in slides_pdfs:
        _validate_upload(upload)          # FIX: reject non-PDF/image uploads
        raw = await upload.read()
        fname = upload.filename or "slides.pdf"
        _total_bytes += len(raw)
        if _total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise HTTPException(413, f"Total upload exceeds {MAX_TOTAL_UPLOAD_BYTES // 1024 // 1024} MB.")
        try:
            marker = f"\n\n{'='*60}\n=== FILE: {fname} ===\n{'='*60}\n\n"
            extracted = (await asyncio.to_thread(extract_text_from_file, raw, fname)
                         if is_image_file(fname)
                         else extract_text_from_file(raw, fname))
            # Renumber pages globally so each page has a unique number across all files.
            # Without this, every PDF resets to Page 1 and the bipartite safety union
            # is blind to inter-file coverage gaps.
            extracted, pages_in_file = _renumber_pages(extracted, _global_page_offset)
            _global_page_offset += pages_in_file
            all_slides_text += marker + extracted + "\n\n"
        except ValueError as e:
            extraction_errors.append(f"{fname}: {e}")
        try:
            if not is_image_file(fname):
                all_slide_images.extend(extract_images_from_file(raw, fname))
        except Exception as e:
            logger.warning("Image extraction failed %s: %s", fname, e)

    for upload in (textbook_pdfs or []):
        raw = await upload.read()
        fname = upload.filename or "textbook.pdf"
        _total_bytes += len(raw)
        if _total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise HTTPException(413, f"Total upload exceeds {MAX_TOTAL_UPLOAD_BYTES // 1024 // 1024} MB.")
        try:
            extracted = (await asyncio.to_thread(extract_text_from_file, raw, fname)
                         if is_image_file(fname)
                         else extract_text_from_file(raw, fname))
            all_textbook_text += extracted + "\n\n"
        except ValueError as e:
            extraction_errors.append(f"{fname}: {e}")
        try:
            if not is_image_file(fname):
                tb_imgs = extract_images_from_file(raw, fname)
                for img in tb_imgs:
                    img.img_id       = f"tb_{img.img_id}"
                    img.source_label = f"Textbook — {img.source_label}"
                all_textbook_images.extend(tb_imgs)
        except Exception:
            pass

    if not all_slides_text.strip() and not all_textbook_text.strip():
        raise HTTPException(422, "Could not extract text from any uploaded files. " + "; ".join(extraction_errors))

    # Step 1b — describe + annotate images (must happen before chunking)
    if all_slide_images and notebook_id:
        async def _desc(img):
            try:
                img.description = await asyncio.to_thread(describe_slide_image, img.data, img.source_label)
            except Exception:
                img.description = f"Figure from {img.source_label}"
        await asyncio.gather(*[_desc(img) for img in all_slide_images])
        try:
            save_images(notebook_id, all_slide_images, clear_existing=True)
        except Exception:
            all_slide_images = []
        for img in all_slide_images:
            pat = re.compile(r'(---\s*' + re.escape(img.source_label) + r'[^\n]*---)', re.IGNORECASE)
            all_slides_text = pat.sub(
                lambda m, ann=f"\n[Figure: {img.description}]": m.group(0) + ann,
                all_slides_text, count=1,
            )

    if all_textbook_images and notebook_id:
        async def _desc_tb(img):
            try:
                img.description = await asyncio.to_thread(describe_slide_image, img.data, img.source_label)
            except Exception:
                img.description = f"Figure from {img.source_label}"
        await asyncio.gather(*[_desc_tb(img) for img in all_textbook_images])
        try:
            save_images(notebook_id, all_textbook_images, clear_existing=False)
            for img in all_textbook_images:
                ext = img.mime.split("/")[-1].replace("jpeg", "jpg")
                textbook_figures_items.append((img, f"/api/images/{notebook_id}/{img.img_id}.{ext}"))
        except Exception:
            all_textbook_images = []

    # Step 2 — chunk + knowledge store
    slide_raw_chunks    = chunk_text(all_slides_text,   max_chars=4000)
    textbook_raw_chunks = chunk_text(all_textbook_text, max_chars=4000)
    textbook_hash       = hashlib.md5(all_textbook_text.encode()).hexdigest()[:16]
    chunks_stored       = None
    if notebook_id:
        try:
            chunks_stored = store_source_chunks(
                nb_id=notebook_id,
                slide_chunks=slide_raw_chunks,
                textbook_chunks=textbook_raw_chunks,
                textbook_hash=textbook_hash,
            )
        except Exception as e:
            logger.warning("Knowledge store write failed: %s", e)

    # Step 2b — semantic chunking
    textbook_semantic_chunks = []
    if all_textbook_text.strip():
        try:
            textbook_semantic_chunks = chunk_textbook(all_textbook_text)
        except Exception as e:
            logger.warning("Textbook semantic chunking failed: %s", e)

    # Step 3 — embed
    embedder, vector_db = Embedder(), VectorDB()
    if textbook_semantic_chunks:
        try:
            loaded = bool(notebook_id) and vector_db.load(notebook_id, expected_hash=textbook_hash)
            if loaded:
                embedder.rebuild_from_chunks(vector_db.chunks)
            else:
                embedder.embed_chunks(textbook_semantic_chunks)
                vector_db.add_chunks(textbook_semantic_chunks)
                if notebook_id: vector_db.add_to_azure(notebook_id, textbook_semantic_chunks)
                if notebook_id:
                    vector_db.save(notebook_id, textbook_hash=textbook_hash)
        except Exception as e:
            logger.warning("Embedding failed: %s", e)

    # Step 4 — slide analysis
    topics = []
    try:
        topics = await analyse_slides(all_slides_text)
    except Exception as e:
        logger.warning("Slide analysis failed: %s", e)

    # Step 5 — retrieval
    topic_contexts: dict[str, str] = {}
    if topics and vector_db.size > 0:
        try:
            retriever      = TopicRetriever(vector_db, embedder)
            topic_contexts = retriever.retrieve_all_topics(topics, nb_id=notebook_id or "")
        except Exception as e:
            logger.warning("Topic retrieval failed: %s", e)

    # Step 5b — match textbook figures to topics
    if textbook_figures_items and topics:
        for img, img_url in textbook_figures_items:
            best = _match_image_to_topic(img.description, topics)
            if best is not None:
                ref = f"\n\n[Textbook Figure: {img.description}]\n![{img.description}]({img_url})"
                topic_contexts[best] = topic_contexts.get(best, "") + ref

    # Step 5c — inline figure map
    topic_figures: dict[str, list] = {}
    if topics and notebook_id:
        for img in all_slide_images:
            ext     = img.mime.split("/")[-1].replace("jpeg", "jpg")
            img_url = f"/api/images/{notebook_id}/{img.img_id}.{ext}"
            matched = None
            for t in topics:
                if img.source_label.lower() in t.slide_text.lower():
                    matched = t.topic
                    break
            if matched is None:
                matched = _match_image_to_topic(img.description, topics)
            if matched:
                topic_figures.setdefault(matched, []).append((img.description, img_url))
        for img, img_url in textbook_figures_items:
            best = _match_image_to_topic(img.description, topics)
            if best:
                topic_figures.setdefault(best, []).append((img.description, img_url))

    # Steps 6–8 — generate + verify
    fused_note, source, pipe_error = None, "local", None
    if topics:
        try:
            fused_note, source = await asyncio.wait_for(
                run_generation_pipeline(topics=topics, topic_contexts=topic_contexts,
                                        proficiency=proficiency, refine=True),
                timeout=PIPELINE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            pipe_error = f"Pipeline timed out after {PIPELINE_TIMEOUT_S}s"
        except Exception as exc:
            pipe_error = f"{type(exc).__name__}: {exc}"

    if not fused_note or len(fused_note.strip()) < 100:
        fused_note = generate_local_note(all_slides_text, all_textbook_text, proficiency)
        source     = "local"

    fused_note = fix_latex_delimiters(_fix_tables(fused_note))
    if fused_note and topic_figures:
        fused_note = _inject_figures_into_sections(fused_note, topic_figures)

    if source != "local":
        try:
            fused_note, _, _ = await _verify_note(fused_note, all_slides_text[:8000], all_textbook_text[:8000])
        except Exception as ve:
            logger.warning("Self-review error: %s", ve)

    if notebook_id:
        try:
            store_note_pages(notebook_id, _note_to_pages(fused_note))
            update_notebook_note(notebook_id, fused_note, proficiency)
        except Exception:
            pass

    return FusionResponse(
        fused_note=fused_note,
        source=source,
        fallback_reason=(f"AI unavailable ({pipe_error}) — offline notes used." if source == "local" and pipe_error
                         else "No AI configured — offline summariser used." if source == "local"
                         else None),
        chunks_stored=chunks_stored,
    )


@router.get("/api/images/{notebook_id}/{img_filename}")
async def serve_slide_image(notebook_id: str, img_filename: str):
    from agents.slide_images import get_image_path
    if not re.fullmatch(r'[a-zA-Z0-9_\-]+', notebook_id) or \
       not re.fullmatch(r'[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+', img_filename):
        raise HTTPException(400, "Invalid image path")
    path = get_image_path(notebook_id, img_filename)
    if not path:
        raise HTTPException(404, f"Image {img_filename} not found")
    ext  = img_filename.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/png")
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "max-age=3600"})


@router.post("/api/upload-fuse", response_model=FusionResponse)
async def upload_fuse(
    slides_pdf:    UploadFile = File(...),
    textbook_pdf:  UploadFile = File(...),
    proficiency:   str = Form("Practitioner"),
    notebook_id:   str = Form(""),
    authorization: Optional[str] = Header(None),
):
    get_current_user(authorization)
    slides_pdf.filename   = slides_pdf.filename   or "slides.pdf"
    textbook_pdf.filename = textbook_pdf.filename or "textbook.pdf"
    return await upload_fuse_multi(
        slides_pdfs=[slides_pdf], textbook_pdfs=[textbook_pdf],
        proficiency=proficiency, notebook_id=notebook_id,
        authorization=authorization,
    )


@router.post("/api/upload-fuse-stream")
async def upload_fuse_stream(
    proficiency:   str              = Form("Practitioner"),
    slides_pdfs:   List[UploadFile] = File(default=[]),
    textbook_pdfs: List[UploadFile] = File(default=[]),
    notebook_id:   Optional[str]    = Form(None),
    authorization: Optional[str]    = Header(None),
):
    """SSE streaming version of upload-fuse-multi."""
    import json as _json
    from agents.pdf_utils import extract_text_from_file, chunk_text
    from agents.knowledge_store import store_source_chunks, store_note_pages
    from agents.notebook_store import update_notebook_note
    from agents.local_summarizer import generate_local_note
    from agents.image_ocr import is_image_file
    from agents.latex_utils import fix_latex_delimiters
    from pipeline.chunker import chunk_textbook
    from pipeline.embedder import Embedder
    from pipeline.vector_db import VectorDB
    from pipeline.slide_analyzer import analyse_slides
    from pipeline.topic_retriever import TopicRetriever
    from pipeline.note_generator import run_generation_pipeline_stream, _fix_tables

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])
    if notebook_id:
        _require_notebook_owner(notebook_id, user)

    all_slides_text, all_textbook_text = "", ""
    _total_bytes, extraction_errors = 0, []
    _global_page_offset = 0   # Global page counter across all uploaded slide files

    for upload in slides_pdfs:
        _validate_upload(upload)          # FIX: reject non-PDF/image uploads
        raw = await upload.read()
        fname = upload.filename or "slides.pdf"
        _total_bytes += len(raw)
        if _total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise HTTPException(413, f"Upload exceeds {MAX_TOTAL_UPLOAD_BYTES//1024//1024} MB limit")
        try:
            marker    = f"\n\n{'='*60}\n=== FILE: {fname} ===\n{'='*60}\n\n"
            extracted = (await asyncio.to_thread(extract_text_from_file, raw, fname)
                         if is_image_file(fname)
                         else extract_text_from_file(raw, fname))
            # Renumber pages globally so each page has a unique number across all files.
            extracted, pages_in_file = _renumber_pages(extracted, _global_page_offset)
            _global_page_offset += pages_in_file
            all_slides_text += marker + extracted + "\n\n"
        except Exception as e:
            extraction_errors.append(f"{fname}: {e}")

    for upload in (textbook_pdfs or []):
        _validate_upload(upload)          # FIX: was missing in stream endpoint
        raw = await upload.read()
        fname = upload.filename or "textbook.pdf"
        _total_bytes += len(raw)
        if _total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise HTTPException(413, f"Upload exceeds {MAX_TOTAL_UPLOAD_BYTES//1024//1024} MB limit")
        try:
            extracted = (await asyncio.to_thread(extract_text_from_file, raw, fname)
                         if is_image_file(fname)
                         else extract_text_from_file(raw, fname))
            all_textbook_text += extracted + "\n\n"
        except Exception as e:
            extraction_errors.append(f"{fname}: {e}")

    if not all_slides_text.strip() and not all_textbook_text.strip():
        raise HTTPException(422, "Could not extract text. " + "; ".join(extraction_errors))

    slide_raw_chunks    = chunk_text(all_slides_text,   max_chars=4000)
    textbook_raw_chunks = chunk_text(all_textbook_text, max_chars=4000)
    textbook_hash       = hashlib.md5(all_textbook_text.encode()).hexdigest()[:16]
    if notebook_id:
        try:
            store_source_chunks(nb_id=notebook_id, slide_chunks=slide_raw_chunks,
                                textbook_chunks=textbook_raw_chunks, textbook_hash=textbook_hash)
        except Exception as e:
            logger.warning("Knowledge store write failed: %s", e)

    textbook_semantic_chunks = []
    if all_textbook_text.strip():
        try:
            textbook_semantic_chunks = chunk_textbook(all_textbook_text)
        except Exception:
            pass

    embedder, vector_db = Embedder(), VectorDB()
    if textbook_semantic_chunks:
        try:
            loaded = bool(notebook_id) and vector_db.load(notebook_id, expected_hash=textbook_hash)
            if loaded:
                embedder.rebuild_from_chunks(vector_db.chunks)
            else:
                embedder.embed_chunks(textbook_semantic_chunks)
                vector_db.add_chunks(textbook_semantic_chunks)
                if notebook_id: vector_db.add_to_azure(notebook_id, textbook_semantic_chunks)
                if notebook_id:
                    vector_db.save(notebook_id, textbook_hash=textbook_hash)
        except Exception as e:
            logger.warning("Embedding failed: %s", e)

    topics = []
    try:
        topics = await analyse_slides(all_slides_text)
    except Exception as e:
        logger.warning("Slide analysis failed: %s", e)

    topic_contexts: dict[str, str] = {}
    if topics and vector_db.size > 0:
        try:
            retriever      = TopicRetriever(vector_db, embedder)
            topic_contexts = retriever.retrieve_all_topics(topics, nb_id=notebook_id or "")
        except Exception:
            pass

    async def event_generator():
        if not topics:
            fallback = generate_local_note(all_slides_text, all_textbook_text, proficiency)
            fallback = fix_latex_delimiters(_fix_tables(fallback))
            if notebook_id:
                try:
                    update_notebook_note(notebook_id, fallback, proficiency)
                except Exception:
                    pass
            yield f"data: {_json.dumps({'type':'done','note':fallback,'source':'local'})}\n\n"
            return

        yield f"data: {_json.dumps({'type':'status','message':'Starting note generation…'})}\n\n"

        final_note, final_source = "", "local"
        try:
            async for event in run_generation_pipeline_stream(topics, topic_contexts, proficiency):
                if event["type"] == "section":
                    event["content"] = fix_latex_delimiters(_fix_tables(event["content"]))
                    final_note += ("\n\n" if final_note else "") + event["content"]
                    final_source = "azure"
                elif event["type"] == "done":
                    final_note   = fix_latex_delimiters(_fix_tables(event.get("note", "") or final_note))
                    final_source = event.get("source", "local")
                    was_corrected, corr_summary = False, ""
                    if final_note and final_source != "local":
                        yield f"data: {_json.dumps({'type':'status','message':'Verifying accuracy against source material…'})}\n\n"
                        try:
                            final_note, was_corrected, corr_summary = await _verify_note(
                                final_note, all_slides_text[:8000], all_textbook_text[:8000]
                            )
                        except Exception as ve:
                            logger.warning("Streaming self-review error (skipping): %s", ve)
                    event.update({
                        "note": final_note, "source": final_source, "verified": True,
                        "corrections_made": 1 if was_corrected else 0,
                        "correction_summary": corr_summary,
                    })
                    if notebook_id and final_note:
                        try:
                            store_note_pages(notebook_id, _note_to_pages(final_note))
                            update_notebook_note(notebook_id, final_note, proficiency)
                        except Exception as e:
                            logger.warning("Stream persist failed: %s", e)
                yield f"data: {_json.dumps(event)}\n\n"
        except Exception as gen_exc:
            # Safety net: generator crashed — emit done with whatever was accumulated
            logger.error("Stream generator crashed: %s", gen_exc, exc_info=True)
            if not final_note:
                final_note = generate_local_note(all_slides_text, all_textbook_text, proficiency)
                final_source = "local"
            final_note = fix_latex_delimiters(_fix_tables(final_note))
            if notebook_id and final_note:
                try:
                    store_note_pages(notebook_id, _note_to_pages(final_note))
                    update_notebook_note(notebook_id, final_note, proficiency)
                except Exception:
                    pass
            yield f"data: {_json.dumps({'type':'done','note':final_note,'source':final_source,'verified':False,'corrections_made':0,'correction_summary':''})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/api/fuse", response_model=FusionResponse)
async def fuse_knowledge(req: FusionRequest, authorization: Optional[str] = Header(None)):
    """Legacy text-based fusion (stores chunks, runs full pipeline)."""
    from agents.pdf_utils import chunk_text
    from agents.knowledge_store import store_source_chunks, store_note_pages
    from agents.notebook_store import update_notebook_note
    from agents.local_summarizer import generate_local_note
    from agents.latex_utils import fix_latex_delimiters
    from pipeline.chunker import chunk_textbook
    from pipeline.embedder import Embedder
    from pipeline.vector_db import VectorDB
    from pipeline.slide_analyzer import analyse_slides
    from pipeline.topic_retriever import TopicRetriever
    from pipeline.note_generator import run_generation_pipeline

    user = get_current_user(authorization)
    _check_llm_rate_limit(user["id"])    # FIX: legacy endpoint had no rate limit
    slide_content    = req.slide_summary[:_PROMPT_SLIDES_BUDGET]
    textbook_content = req.textbook_paragraph[:_PROMPT_TEXTBOOK_BUDGET]
    nb_id            = req.notebook_id

    if nb_id:
        _require_notebook_owner(nb_id, user)   # FIX: no ownership check before writing chunks
        try:
            tb_hash = hashlib.md5(textbook_content.encode()).hexdigest()[:16]
            store_source_chunks(nb_id=nb_id,
                               slide_chunks=chunk_text(slide_content,    max_chars=4000),
                               textbook_chunks=chunk_text(textbook_content, max_chars=4000),
                               textbook_hash=tb_hash)
        except Exception as e:
            logger.warning("/api/fuse: chunk store failed: %s", e)

    fused_note, source = None, "local"
    try:
        topics = await analyse_slides(slide_content)
        if topics:
            embedder, vector_db = Embedder(), VectorDB()
            tb_chunks = chunk_textbook(textbook_content) if textbook_content.strip() else []
            if tb_chunks:
                embedder.embed_chunks(tb_chunks)
                vector_db.add_chunks(tb_chunks)
            topic_contexts: dict[str, str] = {}
            if vector_db.size > 0:
                topic_contexts = TopicRetriever(vector_db, embedder).retrieve_all_topics(topics, nb_id=nb_id or "")
            fused_note, source = await run_generation_pipeline(
                topics=topics, topic_contexts=topic_contexts,
                proficiency=req.proficiency, refine=True,
            )
    except Exception as exc:
        logger.warning("/api/fuse pipeline failed: %s", exc)

    if not fused_note or len(fused_note.strip()) < 100:
        fused_note = generate_local_note(req.slide_summary, req.textbook_paragraph, req.proficiency)
        source     = "local"

    fused_note = fix_latex_delimiters(fused_note)
    if nb_id:
        try:
            store_note_pages(nb_id, _note_to_pages(fused_note))
        except Exception:
            pass

    return FusionResponse(
        fused_note=fused_note,
        source=source,
        fallback_reason=None if source != "local" else "No AI configured — offline summariser used.",
    )
