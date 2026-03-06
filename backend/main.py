"""
AuraGraph - FastAPI + Semantic Kernel Backend  v4
Team: Wowffulls | IIT Roorkee | Challenge: AI Study Buddy

New in v4: Knowledge Store Architecture
────────────────────────────────────────
Every upload now stores ALL source material verbatim in a per-notebook
knowledge store (JSON files in knowledge_store/).

Pipeline:
  1. Upload  → extract text → chunk → store ALL chunks
  2. Generate → retrieve relevant chunks → GPT generates notes by proficiency
  3. Doubt   → retrieve relevant chunks + get exact note page → GPT answers
  4. Mutate  → retrieve relevant chunks + exact note page → GPT rewrites page

This gives every agent full context: what the professor taught, what the
textbook says, and exactly what the student is reading — combined with
OpenAI's own knowledge.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from agents.fusion_agent import FusionAgent
from agents.examiner_agent import ExaminerAgent
from agents.mock_cosmos import get_db, update_node_status
from agents.pdf_utils import extract_text_from_file, chunk_text
from agents.knowledge_store import (
    store_source_chunks, retrieve_relevant_chunks,
    get_chunk_stats, get_all_chunks,
    store_note_pages, get_note_page, get_all_note_pages, update_note_page,
    delete_notebook_store,
)
from agents.local_summarizer import generate_local_note
from agents.local_mutation import local_mutate
from agents.local_examiner import local_examine
from agents.concept_extractor import extract_concepts
from agents.latex_utils import fix_latex_delimiters
from agents.auth_utils import register_user, login_user, validate_token
from agents.notebook_store import (
    create_notebook, get_notebooks, get_notebook,
    update_notebook_note, update_notebook_graph, delete_notebook,
)

load_dotenv()

logger = logging.getLogger("auragraph")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

# ── Context budget ─────────────────────────────────────────────────────────────
# How many chars of retrieved chunks to pass to GPT per source per call.
# Retrieval selects the most relevant chunks first so this is not a hard limit
# on what's STORED — it only limits what goes into the prompt.
_PROMPT_SLIDES_BUDGET   = 24_000   # chars
_PROMPT_TEXTBOOK_BUDGET = 24_000   # chars


# ── Kernel singleton ───────────────────────────────────────────────────────────
kernel        = None
fusion_agent  = None
examiner_agent = None


@asynccontextmanager
async def lifespan(app):
    global kernel, fusion_agent, examiner_agent

    kernel = sk.Kernel()
    kernel.add_service(
        AzureChatCompletion(
            service_id="gpt4o",
            deployment_name=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://mock-endpoint.com/"),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY", "mock-key"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        )
    )

    fusion_agent   = FusionAgent(kernel)
    examiner_agent = ExaminerAgent(kernel)

    logger.info("✅  AuraGraph v4 – Knowledge Store + Azure kernel ready")
    yield
    logger.info("⏹  AuraGraph shutting down")


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AuraGraph API",
    version="0.4.0",
    description="Digital Knowledge Twin – Knowledge Store + Context-Aware Agents",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    token = authorization.split(" ", 1)[1]
    user  = validate_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


def _is_azure_available() -> bool:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key  = os.environ.get("AZURE_OPENAI_API_KEY", "")
    return (
        bool(fusion_agent)
        and "mock-endpoint" not in endpoint
        and api_key not in ("", "mock-key")
    )


def _is_groq_available() -> bool:
    key = os.environ.get("GROQ_API_KEY", "")
    return key not in ("", "your-groq-api-key-here")


async def _groq_chat(messages: list[dict], max_tokens: int = 4000) -> str:
    from openai import OpenAI as _OpenAI
    def _sync():
        client = _OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ.get("GROQ_API_KEY", ""),
        )
        model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        resp  = client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    return await asyncio.to_thread(_sync)


async def _groq_fuse(slide_content: str, textbook_content: str, proficiency: str) -> str:
    from agents.fusion_agent import FUSION_PROMPT
    prompt = (
        FUSION_PROMPT
        .replace("{{$slide_content}}",    slide_content)
        .replace("{{$textbook_content}}", textbook_content)
        .replace("{{$proficiency}}",      proficiency)
    )
    return await _groq_chat([{"role": "user", "content": prompt}])


async def _groq_doubt(
    doubt: str, slide_context: str, textbook_context: str, note_page: str
) -> str:
    from agents.fusion_agent import DOUBT_ANSWER_PROMPT
    prompt = (
        DOUBT_ANSWER_PROMPT
        .replace("{{$doubt}}",            doubt)
        .replace("{{$slide_context}}",    slide_context)
        .replace("{{$textbook_context}}", textbook_context)
        .replace("{{$note_page}}",        note_page)
    )
    return await _groq_chat([{"role": "user", "content": prompt}])


async def _groq_mutate(
    note_page: str, doubt: str, slide_context: str, textbook_context: str
) -> tuple[str, str]:
    from agents.fusion_agent import MUTATION_PROMPT
    prompt = (
        MUTATION_PROMPT
        .replace("{{$note_page}}",        note_page)
        .replace("{{$doubt}}",            doubt)
        .replace("{{$slide_context}}",    slide_context)
        .replace("{{$textbook_context}}", textbook_context)
    )
    text   = await _groq_chat([{"role": "user", "content": prompt}])
    parts  = text.split("|||")
    if len(parts) >= 2:
        return parts[0].strip(), " ".join(p.strip() for p in parts[1:]).strip()
    return text, "Student required additional clarification."


async def _groq_examine(concept_name: str) -> str:
    from agents.examiner_agent import EXAMINER_PROMPT
    prompt = EXAMINER_PROMPT.replace("{{$concept_name}}", concept_name)
    return await _groq_chat([{"role": "user", "content": prompt}])


def _format_chunks_for_prompt(chunks: list[dict], budget: int) -> str:
    """
    Format retrieved chunks into a compact string for GPT.
    Respects char budget — most-relevant chunks go first.
    """
    parts = []
    used  = 0
    for c in chunks:
        header = f"[{c['source'].upper()} — {c.get('heading','') or 'chunk'}]\n"
        body   = c["text"]
        block  = header + body + "\n"
        if used + len(block) > budget:
            # Try to fit a truncated version
            remaining = budget - used - len(header) - 10
            if remaining > 100:
                block = header + body[:remaining].rsplit(" ", 1)[0] + " …\n"
            else:
                break
        parts.append(block)
        used += len(block)
    return "\n---\n".join(parts) if parts else "(no relevant content found)"


def _note_to_pages(note: str) -> list[str]:
    """Split a note string into pages the same way the frontend does."""
    by_h2 = note.split("\n## ")
    if len(by_h2) > 1:
        pages = [by_h2[0]] + ["## " + s for s in by_h2[1:]]
        # Merge very short pages (< 200 chars) into previous
        merged, buf = [], ""
        for p in pages:
            if buf and len(p) < 200:
                buf += "\n\n" + p
            else:
                if buf:
                    merged.append(buf.strip())
                buf = p
        if buf:
            merged.append(buf.strip())
        return [p for p in merged if p.strip()]
    return [note] if note.strip() else []


# ── Schemas ────────────────────────────────────────────────────────────────────
class AuthRequest(BaseModel):
    email:    Optional[str] = None
    username: Optional[str] = None
    password: str

    @property
    def identifier(self) -> str:
        return (self.email or self.username or "").strip()


class FusionResponse(BaseModel):
    fused_note:      str
    source:          str = "azure"
    fallback_reason: Optional[str] = None
    chunks_stored:   Optional[dict] = None   # {"slides": N, "textbook": M}


class DoubtRequest(BaseModel):
    notebook_id: str
    doubt:       str
    page_idx:    int = 0   # which note page the student is viewing


class DoubtResponse(BaseModel):
    answer:      str
    source:      str = "azure"   # "azure" | "local"


class MutationRequest(BaseModel):
    notebook_id:        str
    doubt:              str
    page_idx:           int = 0
    original_paragraph: Optional[str] = None   # kept for backward compat


class MutationResponse(BaseModel):
    mutated_paragraph: str
    concept_gap:       str
    page_idx:          int


class ExaminerRequest(BaseModel):
    concept_name: str


class ExaminerResponse(BaseModel):
    practice_questions: str


class NodeUpdateRequest(BaseModel):
    concept_name: str
    status:       str


class ConceptExtractRequest(BaseModel):
    note:        str
    notebook_id: Optional[str] = None


class NotebookCreateRequest(BaseModel):
    name:   str
    course: str


class NotebookUpdateRequest(BaseModel):
    note:        str
    proficiency: Optional[str] = None


# ── Auth Routes ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "AuraGraph v0.4",
        "azure_configured": _is_azure_available(),
        "groq_configured":  _is_groq_available(),
    }


@app.post("/auth/register")
async def auth_register(req: AuthRequest):
    if not req.identifier:
        raise HTTPException(422, "email or username is required")
    user = register_user(req.identifier, req.password)
    if not user:
        raise HTTPException(409, "Account already exists")
    return user


@app.post("/auth/login")
async def auth_login(req: AuthRequest):
    if not req.identifier:
        raise HTTPException(422, "email or username is required")
    user = login_user(req.identifier, req.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return user


# ── Notebook Routes ────────────────────────────────────────────────────────────
@app.post("/notebooks")
async def new_notebook(req: NotebookCreateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    return create_notebook(user["id"], req.name, req.course)


@app.get("/notebooks")
async def list_notebooks(authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    return get_notebooks(user["id"])


@app.get("/notebooks/{nb_id}")
async def fetch_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb   = get_notebook(nb_id)
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    return nb


@app.patch("/notebooks/{nb_id}/note")
async def save_notebook_note(nb_id: str, req: NotebookUpdateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb   = get_notebook(nb_id)
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    return update_notebook_note(nb_id, req.note, req.proficiency)


@app.delete("/notebooks/{nb_id}")
async def remove_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb   = get_notebook(nb_id)
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    delete_notebook(nb_id)
    delete_notebook_store(nb_id)   # also wipe the knowledge store
    return {"status": "deleted"}


@app.get("/notebooks/{nb_id}/knowledge-stats")
async def get_knowledge_stats(nb_id: str, authorization: Optional[str] = Header(None)):
    """Return stats about what's stored in the knowledge store for this notebook."""
    nb = get_notebook(nb_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    return get_chunk_stats(nb_id)


# ── Upload + Generate Notes ────────────────────────────────────────────────────
@app.post("/api/upload-fuse-multi", response_model=FusionResponse)
async def upload_fuse_multi(
    slides_pdfs:   List[UploadFile] = File(...),
    textbook_pdfs: List[UploadFile] = File(...),
    proficiency:   str = Form("Intermediate"),
    notebook_id:   str = Form(""),
):
    """
    Main upload-and-generate endpoint.
    Implements the full 8-step semantic pipeline from the architecture spec:

      Step 1 — Text Extraction
      Step 2 — Textbook Chunking (400-700 token chunks with chapter/section metadata)
      Step 3 — Embeddings (Azure text-embedding-3-large or TF-IDF fallback)
      Step 4 — Slide Understanding (1 GPT call → structured topic list)
      Step 5 — Topic-Based Retrieval (semantic search per topic)
      Step 6 — Per-Topic Note Generation (N GPT calls, one per topic)
      Step 7 — Merge Notes
      Step 8 — Refinement (1 GPT call)

    Everything is also stored verbatim in the knowledge store so that
    doubt answering and mutation have full source context.

    LLM budget: 1 (slide analysis) + N (topic notes) + 1 (refinement) calls.
    Everything else (chunking, embedding, retrieval) is deterministic.
    """
    from pipeline.chunker import chunk_textbook
    from pipeline.embedder import Embedder
    from pipeline.vector_db import VectorDB
    from pipeline.slide_analyzer import analyse_slides
    from pipeline.topic_retriever import TopicRetriever
    from pipeline.note_generator import run_generation_pipeline

    # ── Step 1: Text Extraction ───────────────────────────────────────────────
    all_slides_text   = ""
    all_textbook_text = ""
    extraction_errors: list[str] = []

    for upload in slides_pdfs:
        raw   = await upload.read()
        fname = upload.filename or "slides.pdf"
        try:
            all_slides_text += extract_text_from_file(raw, fname) + "\n\n"
        except ValueError as e:
            extraction_errors.append(f"{fname}: {e}")
            logger.warning("Slides extraction failed %s: %s", fname, e)

    for upload in textbook_pdfs:
        raw   = await upload.read()
        fname = upload.filename or "textbook.pdf"
        try:
            all_textbook_text += extract_text_from_file(raw, fname) + "\n\n"
        except ValueError as e:
            extraction_errors.append(f"{fname}: {e}")
            logger.warning("Textbook extraction failed %s: %s", fname, e)

    if not all_slides_text.strip() and not all_textbook_text.strip():
        detail = "Could not extract text from any uploaded files."
        if extraction_errors:
            detail += " Errors: " + "; ".join(extraction_errors)
        raise HTTPException(422, detail)

    # ── Step 2: Chunk and Store EVERYTHING verbatim ───────────────────────────
    # Store raw slide + textbook chunks for doubt/mutation retrieval
    slide_raw_chunks    = chunk_text(all_slides_text,   max_chars=4000)
    textbook_raw_chunks = chunk_text(all_textbook_text, max_chars=4000)

    chunks_stored = None
    if notebook_id:
        try:
            chunks_stored = store_source_chunks(nb_id=notebook_id,
                                                slide_chunks=slide_raw_chunks,
                                                textbook_chunks=textbook_raw_chunks)
            logger.info("Knowledge store: %d total chunks for notebook %s",
                        chunks_stored["total"], notebook_id)
        except Exception as e:
            logger.warning("Knowledge store write failed: %s", e)

    # ── Step 2b: Semantic chunking of textbook for vector search ─────────────
    textbook_semantic_chunks = []
    if all_textbook_text.strip():
        try:
            textbook_semantic_chunks = chunk_textbook(all_textbook_text)
            logger.info("Textbook: %d semantic chunks", len(textbook_semantic_chunks))
        except Exception as e:
            logger.warning("Textbook chunking failed: %s", e)

    # ── Step 3: Embeddings ────────────────────────────────────────────────────
    embedder   = Embedder()
    vector_db  = VectorDB()
    embed_backend = "none"

    if textbook_semantic_chunks:
        # Try to load persisted vectors first (fast path on re-generation)
        loaded = False
        if notebook_id:
            try:
                loaded = vector_db.load(notebook_id)
                if loaded:
                    logger.info("Loaded persisted vector index for notebook %s", notebook_id)
            except Exception:
                pass

        if not loaded:
            try:
                embed_backend = embedder.embed_chunks(textbook_semantic_chunks)
                vector_db.add_chunks(textbook_semantic_chunks)
                if notebook_id:
                    vector_db.save(notebook_id)
                logger.info("Embedded %d textbook chunks via %s", len(textbook_semantic_chunks), embed_backend)
            except Exception as e:
                logger.warning("Embedding failed: %s", e)

    # ── Step 4: Slide Understanding (1 LLM call) ──────────────────────────────
    topics = []
    try:
        topics = await analyse_slides(all_slides_text)
        logger.info("Slide analysis: %d topics extracted", len(topics))
    except Exception as e:
        logger.warning("Slide analysis failed: %s", e)

    # ── Step 5: Topic-Based Retrieval ─────────────────────────────────────────
    topic_contexts: dict[str, str] = {}
    if topics and vector_db.size > 0:
        try:
            retriever = TopicRetriever(vector_db, embedder)
            topic_contexts = retriever.retrieve_all_topics(topics)
            logger.info("Retrieved textbook context for %d topics", len(topic_contexts))
        except Exception as e:
            logger.warning("Topic retrieval failed: %s", e)

    # ── Steps 6+7+8: Note Generation + Merge + Refinement ────────────────────
    fused_note  = None
    source      = "local"
    azure_error = None

    if topics:
        try:
            fused_note = await run_generation_pipeline(
                topics=topics,
                topic_contexts=topic_contexts,
                proficiency=proficiency,
                refine=_is_azure_available(),
            )
            source = "azure" if _is_azure_available() else "local"
            logger.info("Pipeline generated %d chars", len(fused_note or ""))
        except Exception as exc:
            azure_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Pipeline generation failed: %s", azure_error)

    # Fallback chain: Groq → local
    if not fused_note or len(fused_note.strip()) < 100:
        if _is_groq_available():
            try:
                logger.info("Falling back to Groq for note generation")
                fused_note = await _groq_fuse(
                    all_slides_text[:_PROMPT_SLIDES_BUDGET],
                    all_textbook_text[:_PROMPT_TEXTBOOK_BUDGET],
                    proficiency,
                )
                source = "groq"
                logger.info("Groq generated %d chars", len(fused_note or ""))
            except Exception as exc:
                logger.warning("Groq fuse failed: %s", exc)
        if not fused_note or len(fused_note.strip()) < 100:
            logger.info("Falling back to local summarizer")
            fused_note = generate_local_note(all_slides_text, all_textbook_text, proficiency)
            source     = "local"

    fused_note = fix_latex_delimiters(fused_note)

    # ── Store note pages ──────────────────────────────────────────────────────
    if notebook_id:
        try:
            pages = _note_to_pages(fused_note)
            store_note_pages(notebook_id, pages)
            logger.info("Stored %d note pages for notebook %s", len(pages), notebook_id)
        except Exception as e:
            logger.warning("Note page store failed: %s", e)

        try:
            update_notebook_note(notebook_id, fused_note, proficiency)
        except Exception:
            pass

    fallback_warning = None
    if source == "local" and azure_error:
        fallback_warning = f"Azure unavailable ({azure_error}) — offline notes used."
    elif source == "local":
        fallback_warning = "Azure not configured — offline summariser used."

    return FusionResponse(
        fused_note=fused_note,
        source=source,
        fallback_reason=fallback_warning,
        chunks_stored=chunks_stored,
    )


# Backward-compat alias
@app.post("/api/upload-fuse", response_model=FusionResponse)
async def upload_fuse(
    slides_pdf:   UploadFile = File(...),
    textbook_pdf: UploadFile = File(...),
    proficiency:  str = Form("Intermediate"),
    notebook_id:  str = Form(""),
):
    """Single-file version — delegates to upload_fuse_multi."""
    slides_pdf.filename   = slides_pdf.filename   or "slides.pdf"
    textbook_pdf.filename = textbook_pdf.filename or "textbook.pdf"
    return await upload_fuse_multi(
        slides_pdfs=[slides_pdf],
        textbook_pdfs=[textbook_pdf],
        proficiency=proficiency,
        notebook_id=notebook_id,
    )


# ── Doubt Answering ────────────────────────────────────────────────────────────
@app.post("/api/doubt", response_model=DoubtResponse)
async def answer_doubt(req: DoubtRequest):
    """
    Answer a student's doubt using:
    - Relevant slide chunks from the knowledge store
    - Relevant textbook chunks from the knowledge store
    - The exact note page the student is reading
    - OpenAI's own knowledge (via the prompt context)
    """
    nb_id    = req.notebook_id
    doubt    = req.doubt
    page_idx = req.page_idx

    # Retrieve relevant source chunks
    slide_hits    = retrieve_relevant_chunks(nb_id, doubt, top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(nb_id, doubt, top_k=6, source_filter="textbook")
    slide_context    = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_context = _format_chunks_for_prompt(textbook_hits, 8_000)

    # Get the exact note page
    note_page = get_note_page(nb_id, page_idx) or ""

    if _is_azure_available():
        try:
            answer = await fusion_agent.answer_doubt(
                doubt=doubt,
                slide_context=slide_context,
                textbook_context=textbook_context,
                note_page=note_page,
            )
            return DoubtResponse(answer=fix_latex_delimiters(answer), source="azure")
        except Exception as exc:
            logger.warning("Azure doubt failed: %s", exc)

    if _is_groq_available():
        try:
            answer = await _groq_doubt(doubt, slide_context, textbook_context, note_page)
            return DoubtResponse(answer=fix_latex_delimiters(answer), source="groq")
        except Exception as exc:
            logger.warning("Groq doubt failed: %s", exc)

    # Local fallback: combine contexts into a simple response
    from agents.local_mutation import _diagnose_gap, _build_analogy_hint
    gap     = _diagnose_gap(doubt)
    analogy = _build_analogy_hint(doubt)
    answer  = f"**{gap}**\n\n{analogy}"
    if note_page:
        answer += f"\n\n*From your notes:* {note_page[:300]}…"
    return DoubtResponse(answer=fix_latex_delimiters(answer), source="local")


# ── Mutation ───────────────────────────────────────────────────────────────────
@app.post("/api/mutate", response_model=MutationResponse)
async def mutate_note(req: MutationRequest):
    """
    Rewrite a note page using full source context.
    Uses:
    - The exact note page from the knowledge store (by page_idx)
    - Relevant slide chunks about the doubted topic
    - Relevant textbook chunks about the doubted topic
    - The student's doubt
    """
    nb_id    = req.notebook_id
    doubt    = req.doubt
    page_idx = req.page_idx

    # Get exact note page from store (more reliable than what frontend sends)
    note_page = get_note_page(nb_id, page_idx)
    if note_page is None:
        # Fallback: use original_paragraph from request if page not in store
        note_page = req.original_paragraph or ""

    # Retrieve relevant source chunks for this doubt
    slide_hits    = retrieve_relevant_chunks(nb_id, doubt + " " + note_page[:200], top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(nb_id, doubt + " " + note_page[:200], top_k=6, source_filter="textbook")
    slide_context    = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_context = _format_chunks_for_prompt(textbook_hits, 8_000)

    mutated = None
    gap     = ""

    if _is_azure_available():
        try:
            mutated, gap = await fusion_agent.mutate(
                note_page=note_page,
                doubt=doubt,
                slide_context=slide_context,
                textbook_context=textbook_context,
            )
        except Exception as exc:
            logger.warning("Azure mutation failed: %s", exc)

    if mutated is None and _is_groq_available():
        try:
            mutated, gap = await _groq_mutate(note_page, doubt, slide_context, textbook_context)
        except Exception as exc:
            logger.warning("Groq mutation failed: %s", exc)

    if mutated is None:
        mutated, gap = local_mutate(note_page, doubt)

    mutated = fix_latex_delimiters(mutated)

    # Update the stored note page
    if nb_id:
        try:
            updated = update_note_page(nb_id, page_idx, mutated)
            if updated:
                # Rebuild full note from pages and persist
                pages = get_all_note_pages(nb_id)
                full_note = "\n\n".join(pages)
                update_notebook_note(nb_id, full_note)
                logger.info("Mutated page %d for notebook %s", page_idx, nb_id)
        except Exception as e:
            logger.warning("Page update failed: %s", e)

    update_node_status("Convolution Theorem", "partial")

    return MutationResponse(
        mutated_paragraph=mutated,
        concept_gap=gap,
        page_idx=page_idx,
    )


# ── Examiner ───────────────────────────────────────────────────────────────────
@app.post("/api/examine", response_model=ExaminerResponse)
async def examine_concept(req: ExaminerRequest):
    if examiner_agent and _is_azure_available():
        try:
            questions = await examiner_agent.examine(req.concept_name)
            return ExaminerResponse(practice_questions=fix_latex_delimiters(questions))
        except Exception as exc:
            logger.warning("Azure examiner failed: %s", exc)
    if _is_groq_available():
        try:
            questions = await _groq_examine(req.concept_name)
            return ExaminerResponse(practice_questions=fix_latex_delimiters(questions))
        except Exception as exc:
            logger.warning("Groq examiner failed: %s", exc)
    questions = local_examine(req.concept_name)
    return ExaminerResponse(practice_questions=fix_latex_delimiters(questions))


# ── Graph Routes ───────────────────────────────────────────────────────────────
@app.get("/api/graph")
async def get_graph():
    return get_db()


@app.post("/api/graph/update")
async def update_graph(req: NodeUpdateRequest):
    updated = update_node_status(req.concept_name, req.status)
    if not updated:
        raise HTTPException(404, "Node not found")
    return {"status": "success", "node": updated}


@app.post("/api/extract-concepts")
async def extract_concepts_endpoint(req: ConceptExtractRequest):
    graph = extract_concepts(req.note)
    if req.notebook_id:
        update_notebook_graph(req.notebook_id, graph)
    return graph


@app.get("/notebooks/{nb_id}/graph")
async def get_notebook_graph(nb_id: str, authorization: Optional[str] = Header(None)):
    nb = get_notebook(nb_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    return nb.get("graph", {"nodes": [], "edges": []})


@app.post("/notebooks/{nb_id}/graph/update")
async def update_notebook_graph_node(
    nb_id: str,
    req: NodeUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    nb = get_notebook(nb_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    graph = nb.get("graph", {"nodes": [], "edges": []})
    for node in graph["nodes"]:
        if node["label"].lower() == req.concept_name.lower():
            node["status"] = req.status
            update_notebook_graph(nb_id, graph)
            return {"status": "success", "node": node}
    raise HTTPException(404, "Concept node not found")


# ── Legacy /api/fuse (text-based) kept for compat ─────────────────────────────
class FusionRequest(BaseModel):
    slide_summary:       str
    textbook_paragraph:  str
    proficiency:         str = "Intermediate"
    notebook_id:         Optional[str] = None


@app.post("/api/fuse", response_model=FusionResponse)
async def fuse_knowledge(req: FusionRequest):
    slide_content    = req.slide_summary[:_PROMPT_SLIDES_BUDGET]
    textbook_content = req.textbook_paragraph[:_PROMPT_TEXTBOOK_BUDGET]

    fused_note  = None
    source      = "local"
    azure_error = None

    if _is_azure_available():
        try:
            fused_note = await fusion_agent.fuse(slide_content, textbook_content, req.proficiency)
            source     = "azure"
        except Exception as exc:
            azure_error = str(exc)

    if fused_note is None and _is_groq_available():
        try:
            fused_note = await _groq_fuse(slide_content, textbook_content, req.proficiency)
            source     = "groq"
        except Exception as exc:
            logger.warning("Groq fuse failed: %s", exc)

    if fused_note is None:
        fused_note = generate_local_note(req.slide_summary, req.textbook_paragraph, req.proficiency)

    fused_note = fix_latex_delimiters(fused_note)

    if req.notebook_id:
        try:
            pages = _note_to_pages(fused_note)
            store_note_pages(req.notebook_id, pages)
        except Exception:
            pass

    return FusionResponse(
        fused_note=fused_note,
        source=source,
        fallback_reason=azure_error,
    )
