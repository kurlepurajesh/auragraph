"""
AuraGraph — FastAPI + Semantic Kernel Backend  v5
Team: Wowffulls | IIT Roorkee | Challenge: AI Study Buddy

All 32 critic findings resolved:
  A1  /knowledge-stats — added ownership check
  A2  /api/graph       — requires auth
  A3  /api/doubt       — requires auth
  A4  /api/mutate      — requires auth
  A5  /api/examine     — requires auth
  A6  Hardcoded mock credentials removed from lifespan
  A7  Hardcoded "Convolution Theorem" replaced with dynamic concept extraction

  B1  _note_to_pages: re.split(r'(?m)^(?=## )') — first ## section no longer lost
  B3  Image annotation happens BEFORE chunking — knowledge store sees figure refs
  B4  Fresh Embedder + loaded VectorDB: embedder.rebuild_from_chunks() called
  (B2 was already correct; B5/B6 were already correct)

  C1  note_generator: asyncio.to_thread replaced with httpx async calls
  C2  refine_notes threshold 0.6 → 0.3 (good compressions kept)
  C3  Semaphore reads LLM_CONCURRENCY env var (default 1 for Groq free tier)

  D1–D4  slide_images.py: EMU calc, doc.close order, per-page budget, clear_existing
  E1–E3  image_ocr.py: to_thread in caller, image resize, magic-byte MIME
  F3     vector_db save/load store textbook_hash for staleness detection
  G2     slide_analyzer: chunked analysis — no more 40 k hard truncation

  H1–H4  lecture_notes_generator/ standalone (separate files, see that dir)

  L1  /api/fuse now stores source chunks (doubt/mutate work after it)
  L2  VectorDB.delete called on notebook deletion
  L3  Single mutate parser via FusionAgent._parse_mutate_response
  L4  /api/fuse delegates to run_generation_pipeline

  J1  handleDoubt page_idx bug is in frontend NotebookWorkspace.jsx
      (MutateModal already sends page_idx correctly; the standalone
       "Ask doubt" path in the modal also sends page_idx — see jsx fix)

  K1–K9  Missing tests added to test_notes_pipeline.py (separate file)
"""

import asyncio
import hashlib
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from agents.fusion_agent import FusionAgent
from agents.examiner_agent import ExaminerAgent
from agents.mock_cosmos import get_db, update_node_status
from agents.pdf_utils import extract_text_from_file, chunk_text
from agents.knowledge_store import (
    store_source_chunks, retrieve_relevant_chunks,
    get_chunk_stats,
    store_note_pages, get_note_page, get_all_note_pages, update_note_page,
    delete_notebook_store,
)
from agents.local_summarizer import generate_local_note
from agents.local_mutation import local_mutate
from agents.local_examiner import local_examine
from agents.concept_extractor import extract_concepts
from agents.latex_utils import fix_latex_delimiters
from agents.auth_utils import register_user, login_user, validate_token
from agents.slide_images import extract_images_from_file, save_images, get_image_path
from agents.image_ocr import describe_slide_image
from agents.notebook_store import (
    create_notebook, get_notebooks, get_notebook,
    update_notebook_note, update_notebook_graph, delete_notebook,
)

load_dotenv()

logger = logging.getLogger("auragraph")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

_PROMPT_SLIDES_BUDGET   = 24_000
_PROMPT_TEXTBOOK_BUDGET = 24_000

kernel         = None
fusion_agent   = None
examiner_agent = None


@asynccontextmanager
async def lifespan(app):
    global kernel, fusion_agent, examiner_agent

    # FIX A6: No hardcoded "mock-key" fallback — if env vars absent the kernel
    # is initialised with placeholder strings and _is_azure_available() returns False.
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://placeholder.invalid/")
    api_key  = os.environ.get("AZURE_OPENAI_API_KEY",  "placeholder")

    kernel = sk.Kernel()
    kernel.add_service(
        AzureChatCompletion(
            service_id="gpt4o",
            deployment_name=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            endpoint=endpoint,
            api_key=api_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        )
    )
    fusion_agent   = FusionAgent(kernel)
    examiner_agent = ExaminerAgent(kernel)
    logger.info("✅  AuraGraph v5 — all 32 critic fixes applied")
    yield
    logger.info("⏹  AuraGraph shutting down")


app = FastAPI(
    title="AuraGraph API",
    version="0.5.0",
    description="Digital Knowledge Twin — fully hardened v5",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth helpers ───────────────────────────────────────────────────────────────

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    token = authorization.split(" ", 1)[1]
    user  = validate_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


def _require_notebook_owner(nb_id: str, user: dict) -> dict:
    """Load notebook and assert it belongs to the requesting user."""
    nb = get_notebook(nb_id)
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    return nb


# ── LLM availability ───────────────────────────────────────────────────────────

def _is_azure_available() -> bool:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key  = os.environ.get("AZURE_OPENAI_API_KEY",  "")
    return (
        bool(fusion_agent)
        and bool(endpoint)
        and bool(api_key)
        and "placeholder" not in endpoint.lower()
        and "mock"        not in endpoint.lower()
        and "placeholder" not in api_key.lower()
        and "mock"        not in api_key.lower()
    )


def _is_groq_available() -> bool:
    key = os.environ.get("GROQ_API_KEY", "")
    return bool(key) and not key.startswith("your-")


# ── Groq helpers ───────────────────────────────────────────────────────────────

async def _groq_chat(messages: list[dict], max_tokens: int = 4000) -> str:
    """
    True-async Groq call via httpx — no thread-pool blocking.
    FIX C1 (main.py): was asyncio.to_thread(OpenAI()) — now httpx, consistent
    with note_generator.py.  Includes one 429 retry with 6 s back-off.
    """
    import httpx
    api_key = os.environ.get("GROQ_API_KEY", "")
    model   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    payload = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for attempt in range(2):
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload, headers=headers,
            )
        if resp.status_code == 429 and attempt == 0:
            wait = int(resp.headers.get("Retry-After", "6"))
            logger.warning("Groq 429 — waiting %d s before retry", wait)
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    raise RuntimeError("Groq rate-limited after retry")


async def _groq_fuse(slide_content: str, textbook_content: str, proficiency: str) -> str:
    from agents.fusion_agent import FUSION_PROMPT
    prompt = (
        FUSION_PROMPT
        .replace("{{$slide_content}}",    slide_content)
        .replace("{{$textbook_content}}", textbook_content)
        .replace("{{$proficiency}}",      proficiency)
    )
    return await _groq_chat([{"role": "user", "content": prompt}])


async def _groq_doubt(doubt, slide_ctx, textbook_ctx, note_page) -> str:
    from agents.fusion_agent import DOUBT_ANSWER_PROMPT
    prompt = (
        DOUBT_ANSWER_PROMPT
        .replace("{{$doubt}}",            doubt)
        .replace("{{$slide_context}}",    slide_ctx)
        .replace("{{$textbook_context}}", textbook_ctx)
        .replace("{{$note_page}}",        note_page)
    )
    return await _groq_chat([{"role": "user", "content": prompt}])


async def _groq_examine(concept_name: str) -> str:
    from agents.examiner_agent import EXAMINER_PROMPT
    prompt = EXAMINER_PROMPT.replace("{{$concept_name}}", concept_name)
    return await _groq_chat([{"role": "user", "content": prompt}])


# FIX L3: single mutate path — delegates to FusionAgent._parse_mutate_response
async def _llm_mutate(
    note_page: str, doubt: str, slide_ctx: str, textbook_ctx: str
) -> tuple[Optional[str], Optional[str], str]:
    """
    Try Azure (via SK) then Groq for mutation.
    Both use FusionAgent._parse_mutate_response — no duplicate parsers.
    Returns (mutated_text, gap, source) where source is 'azure'|'groq'|'none'.
    """
    if _is_azure_available():
        try:
            mutated, gap = await fusion_agent.mutate(
                note_page=note_page, doubt=doubt,
                slide_context=slide_ctx, textbook_context=textbook_ctx,
            )
            return mutated, gap, "azure"
        except Exception as e:
            logger.warning("Azure mutation failed: %s", e)

    if _is_groq_available():
        try:
            from agents.fusion_agent import MUTATION_PROMPT
            prompt = (
                MUTATION_PROMPT
                .replace("{{$note_page}}",        note_page)
                .replace("{{$doubt}}",            doubt)
                .replace("{{$slide_context}}",    slide_ctx)
                .replace("{{$textbook_context}}", textbook_ctx)
            )
            text = await _groq_chat([{"role": "user", "content": prompt}])
            # FIX L3: reuse the canonical parser
            mutated, gap = FusionAgent._parse_mutate_response(text)
            return mutated, gap, "groq"
        except Exception as e:
            logger.warning("Groq mutation failed: %s", e)

    return None, None, "none"


# ── Utility helpers ────────────────────────────────────────────────────────────

def _format_chunks_for_prompt(chunks: list[dict], budget: int) -> str:
    parts, used = [], 0
    for c in chunks:
        header = f"[{c['source'].upper()} — {c.get('heading','') or 'chunk'}]\n"
        body   = c["text"]
        block  = header + body + "\n"
        if used + len(block) > budget:
            remaining = budget - used - len(header) - 10
            if remaining > 100:
                block = header + body[:remaining].rsplit(" ", 1)[0] + " …\n"
            else:
                break
        parts.append(block)
        used += len(block)
    return "\n---\n".join(parts) if parts else "(no relevant content found)"


def _match_image_to_topic(description: str, topics) -> Optional[str]:
    STOP = {
        'a','an','the','is','are','of','in','on','at','to','for','with',
        'its','this','that','these','those','it','as','by','be','was',
        'were','showing','shows','figure','diagram','image','graph',
        'chart','plot','from','and','or','not','each','which','where',
    }
    def _tokens(s):
        return set(re.sub(r'[^\w\s]', '', s.lower()).split()) - STOP

    desc_tokens = _tokens(description)
    if not desc_tokens:
        return None
    best_score, best_topic = 0.0, None
    for t in topics:
        combined = t.topic + ' ' + ' '.join(getattr(t, 'key_points', [])[:4])
        t_tokens = _tokens(combined)
        if not t_tokens:
            continue
        inter = len(desc_tokens & t_tokens)
        union = len(desc_tokens | t_tokens)
        score = inter / union if union else 0.0
        if score > best_score:
            best_score, best_topic = score, t.topic
    return best_topic if best_score > 0.04 else None


def _inject_figures_into_sections(note: str, topic_figures: dict) -> str:
    if not topic_figures:
        return note
    result = []
    for line in note.split('\n'):
        result.append(line)
        if line.startswith('## '):
            heading_text = line[3:].strip().lower()
            matched_figs = None
            for tname, figs in topic_figures.items():
                tl = tname.lower()
                if tl == heading_text or tl in heading_text or heading_text in tl:
                    matched_figs = figs
                    break
            if matched_figs:
                result.append('')
                for description, url in matched_figs:
                    safe_alt = description.replace('"', "'")
                    result.append(f'![{safe_alt}]({url})')
                    result.append(f'*{safe_alt}*')
                    result.append('')
    return '\n'.join(result)


# FIX B1 + PAGE-SYNC: _note_to_pages now exactly mirrors frontend useMemo pagination.
# Frontend groups ## sections into ~3000-char pages; old backend merged only < 200-char
# sections, producing different page indices.  Mismatched indices caused /api/doubt and
# /api/mutate to retrieve wrong note context for the page the student was actually viewing.
def _note_to_pages(note: str) -> list[str]:
    """
    Split a note into pages that exactly mirror the frontend useMemo pagination
    (NotebookWorkspace.jsx — pages computed from note state).

    Algorithm (ported from JS):
      1. re.split(r'(?m)^(?=## )') — every ## heading starts a new section.
      2. Group sections greedily: add to buffer until adding the next would
         exceed TARGET (3000 chars) AND the buffer is already > 200 chars.
      3. Flush remaining buffer.
    """
    if not note.strip():
        return []

    TARGET   = 3000
    sections = re.split(r'(?m)^(?=## )', note.strip())
    parts    = [p.strip() for p in sections if p.strip()]

    if not parts:
        return [note.strip()]

    merged, buf = [], ""
    for s in parts:
        if buf and len(buf) + len(s) + 2 > TARGET and len(buf) > 200:
            merged.append(buf.strip())
            buf = s
        else:
            buf = (buf + "\n\n" + s) if buf else s
    if buf:
        merged.append(buf.strip())
    return [p for p in merged if p.strip()]


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
    chunks_stored:   Optional[dict] = None


class DoubtRequest(BaseModel):
    notebook_id: str
    doubt:       str
    page_idx:    int = 0


class DoubtResponse(BaseModel):
    answer: str
    source: str = "azure"


class MutationRequest(BaseModel):
    notebook_id:        str
    doubt:              str
    page_idx:           int = 0
    original_paragraph: Optional[str] = None


class MutationResponse(BaseModel):
    mutated_paragraph: str
    concept_gap:       str
    page_idx:          int
    source:            str = "azure"
    can_mutate:        bool = True


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


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":           "ok",
        "service":          "AuraGraph v0.5",
        "azure_configured": _is_azure_available(),
        "groq_configured":  _is_groq_available(),
        "llm_concurrency":  int(os.environ.get("LLM_CONCURRENCY", "1")),
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


# ── Notebook routes ────────────────────────────────────────────────────────────

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
    return _require_notebook_owner(nb_id, user)


@app.patch("/notebooks/{nb_id}/note")
async def save_notebook_note(
    nb_id: str, req: NotebookUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    return update_notebook_note(nb_id, req.note, req.proficiency)


@app.delete("/notebooks/{nb_id}")
async def remove_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)
    delete_notebook(nb_id)
    delete_notebook_store(nb_id)
    # FIX L2: also wipe vector index from disk
    from pipeline.vector_db import VectorDB
    VectorDB.delete(nb_id)
    return {"status": "deleted"}


# FIX A1: added ownership check (was only checking existence)
@app.get("/notebooks/{nb_id}/knowledge-stats")
async def get_knowledge_stats(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    _require_notebook_owner(nb_id, user)   # FIX A1
    return get_chunk_stats(nb_id)


# ── Upload + Generate Notes ────────────────────────────────────────────────────

@app.post("/api/upload-fuse-multi", response_model=FusionResponse)
async def upload_fuse_multi(
    slides_pdfs:   List[UploadFile] = File(...),
    textbook_pdfs: Optional[List[UploadFile]] = File(default=None),
    proficiency:   str = Form("Practitioner"),
    notebook_id:   str = Form(""),
    authorization: Optional[str] = Header(None),
):
    """
    Full 8-step semantic pipeline with all critic fixes applied.
    Key order of operations (all order-dependent fixes marked):
      Step 1   — extract text + images from all files
      Step 1b  — describe images async (FIX E1: to_thread)
                 annotate slide text (FIX B3: BEFORE chunking)
      Step 2   — chunk raw text and store verbatim in knowledge store
                 (FIX B3: annotation already in text; FIX F3: textbook_hash)
      Step 2b  — semantic chunking for vector search
      Step 3   — embed chunks (FIX F3: hash-aware load; FIX B4: rebuild TF-IDF)
      Step 4   — slide analysis (FIX G2: chunked, no 40k truncation)
      Step 5   — topic retrieval
      Step 5b  — figure→topic matching
      Steps 6+7+8 — note generation + merge + refinement (FIX C1/C2/C3)
    """
    get_current_user(authorization)  # FIX: require auth to prevent anonymous LLM abuse
    from pipeline.chunker import chunk_textbook
    from pipeline.embedder import Embedder
    from pipeline.vector_db import VectorDB
    from pipeline.slide_analyzer import analyse_slides
    from pipeline.topic_retriever import TopicRetriever
    from pipeline.note_generator import run_generation_pipeline

    # ── Step 1: Text + image extraction ──────────────────────────────────────
    all_slides_text   = ""
    all_textbook_text = ""
    extraction_errors: list[str] = []
    all_slide_images:     list = []
    all_textbook_images:  list = []
    textbook_figures_items: list = []

    for upload in slides_pdfs:
        raw   = await upload.read()
        fname = upload.filename or "slides.pdf"
        try:
            all_slides_text += extract_text_from_file(raw, fname) + "\n\n"
        except ValueError as e:
            extraction_errors.append(f"{fname}: {e}")
            logger.warning("Slides extraction failed %s: %s", fname, e)
        try:
            imgs = extract_images_from_file(raw, fname)
            all_slide_images.extend(imgs)
        except Exception as e:
            logger.warning("Image extraction failed %s: %s", fname, e)

    for upload in (textbook_pdfs or []):
        raw   = await upload.read()
        fname = upload.filename or "textbook.pdf"
        try:
            all_textbook_text += extract_text_from_file(raw, fname) + "\n\n"
        except ValueError as e:
            extraction_errors.append(f"{fname}: {e}")
            logger.warning("Textbook extraction failed %s: %s", fname, e)
        try:
            tb_imgs = extract_images_from_file(raw, fname)
            for img in tb_imgs:
                img.img_id       = f"tb_{img.img_id}"
                img.source_label = f"Textbook — {img.source_label}"
            all_textbook_images.extend(tb_imgs)
        except Exception as e:
            logger.warning("Textbook image extraction failed %s: %s", fname, e)

    if not all_slides_text.strip() and not all_textbook_text.strip():
        detail = "Could not extract text from any uploaded files."
        if extraction_errors:
            detail += " Errors: " + "; ".join(extraction_errors)
        raise HTTPException(422, detail)

    # ── Step 1b: Describe images + annotate slide text (FIX B3 + E1) ─────────
    # FIX E1: describe_slide_image is sync — wrap in to_thread
    # FIX B3: annotation MUST happen before chunk_text() below
    if all_slide_images and notebook_id:
        logger.info("Describing %d slide images (async)…", len(all_slide_images))

        async def _desc(img):
            try:
                img.description = await asyncio.to_thread(
                    describe_slide_image, img.data, img.source_label
                )
            except Exception as e:
                img.description = f"Figure from {img.source_label}"
                logger.debug("describe_slide_image error: %s", e)

        await asyncio.gather(*[_desc(img) for img in all_slide_images])

        # FIX D4: clear_existing=True so re-upload of same notebook doesn't accumulate stale files
        try:
            save_images(notebook_id, all_slide_images, clear_existing=True)
        except Exception as e:
            logger.warning("Slide image save failed: %s", e)
            all_slide_images = []

        # FIX B3: annotate slide text NOW — before chunk_text() on line below
        for img in all_slide_images:
            marker_pattern = re.compile(
                r'(---\s*' + re.escape(img.source_label) + r'[^\n]*---)',
                re.IGNORECASE,
            )
            all_slides_text = marker_pattern.sub(
                lambda m, ann=f"\n[Figure: {img.description}]": m.group(0) + ann,
                all_slides_text, count=1,
            )
        logger.info("Annotated %d slide images into slide text (before chunking)", len(all_slide_images))

    elif all_slide_images:
        logger.info("No notebook_id — slide image save skipped")

    if all_textbook_images and notebook_id:
        logger.info("Describing %d textbook images (async)…", len(all_textbook_images))

        async def _desc_tb(img):
            try:
                img.description = await asyncio.to_thread(
                    describe_slide_image, img.data, img.source_label
                )
            except Exception as e:
                img.description = f"Figure from {img.source_label}"

        await asyncio.gather(*[_desc_tb(img) for img in all_textbook_images])
        try:
            save_images(notebook_id, all_textbook_images, clear_existing=False)
            for img in all_textbook_images:
                ext = img.mime.split("/")[-1].replace("jpeg", "jpg")
                textbook_figures_items.append(
                    (img, f"/api/images/{notebook_id}/{img.img_id}.{ext}")
                )
        except Exception as e:
            logger.warning("Textbook image save failed: %s", e)
            all_textbook_images = []

    # ── Step 2: Chunk raw text + store in knowledge store (FIX B3, F3) ───────
    slide_raw_chunks    = chunk_text(all_slides_text,   max_chars=4000)
    textbook_raw_chunks = chunk_text(all_textbook_text, max_chars=4000)
    textbook_hash       = hashlib.md5(all_textbook_text.encode()).hexdigest()[:16]

    chunks_stored = None
    if notebook_id:
        try:
            chunks_stored = store_source_chunks(
                nb_id=notebook_id,
                slide_chunks=slide_raw_chunks,
                textbook_chunks=textbook_raw_chunks,
                textbook_hash=textbook_hash,  # FIX F3
            )
            logger.info("Knowledge store: %d chunks for %s", chunks_stored["total"], notebook_id)
        except Exception as e:
            logger.warning("Knowledge store write failed: %s", e)

    # ── Step 2b: Semantic chunking for vector search ──────────────────────────
    textbook_semantic_chunks = []
    if all_textbook_text.strip():
        try:
            textbook_semantic_chunks = chunk_textbook(all_textbook_text)
            logger.info("Textbook: %d semantic chunks", len(textbook_semantic_chunks))
        except Exception as e:
            logger.warning("Textbook semantic chunking failed: %s", e)

    # ── Step 3: Embeddings (FIX F3 staleness, FIX B4 TF-IDF rebuild) ─────────
    embedder  = Embedder()
    vector_db = VectorDB()

    if textbook_semantic_chunks:
        loaded = False
        if notebook_id:
            try:
                # FIX F3: pass hash — load() rejects stale index automatically
                loaded = vector_db.load(notebook_id, expected_hash=textbook_hash)
                if loaded:
                    logger.info("Loaded fresh vector index for %s", notebook_id)
            except Exception:
                pass

        if loaded:
            # FIX B4: rebuild TF-IDF so embed_query works on a fresh Embedder
            try:
                embedder.rebuild_from_chunks(vector_db.chunks)
                logger.info("Rebuilt TF-IDF from %d loaded chunks", vector_db.size)
            except Exception as e:
                logger.warning("Embedder rebuild failed (%s) — re-embedding", e)
                loaded = False

        if not loaded:
            try:
                backend = embedder.embed_chunks(textbook_semantic_chunks)
                vector_db.add_chunks(textbook_semantic_chunks)
                if notebook_id:
                    vector_db.save(notebook_id, textbook_hash=textbook_hash)
                logger.info("Embedded %d chunks via %s", len(textbook_semantic_chunks), backend)
            except Exception as e:
                logger.warning("Embedding failed: %s", e)

    # ── Step 4: Slide understanding (FIX G2: no hard truncation) ─────────────
    topics = []
    try:
        topics = await analyse_slides(all_slides_text)
        logger.info("Slide analysis: %d topics", len(topics))
    except Exception as e:
        logger.warning("Slide analysis failed: %s", e)

    # ── Step 5: Topic-based retrieval ─────────────────────────────────────────
    topic_contexts: dict[str, str] = {}
    if topics and vector_db.size > 0:
        try:
            retriever = TopicRetriever(vector_db, embedder)
            topic_contexts = retriever.retrieve_all_topics(topics)
            logger.info("Retrieved context for %d topics", len(topic_contexts))
        except Exception as e:
            logger.warning("Topic retrieval failed: %s", e)

    # ── Step 5b: Match textbook figures to topics ─────────────────────────────
    if textbook_figures_items and topics:
        for img, img_url in textbook_figures_items:
            best = _match_image_to_topic(img.description, topics)
            if best is not None:
                ref = f"\n\n[Textbook Figure: {img.description}]\n![{img.description}]({img_url})"
                topic_contexts[best] = topic_contexts.get(best, "") + ref

    # ── Step 5c: Build topic_figures map for inline injection ─────────────────
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
        if topic_figures:
            logger.info("Inline figures: %d topics, %d figures total",
                        len(topic_figures), sum(len(v) for v in topic_figures.values()))

    # ── Steps 6+7+8: Generate + merge + refine ────────────────────────────────
    fused_note = None
    source     = "local"
    pipe_error = None

    if topics:
        try:
            fused_note, source = await run_generation_pipeline(
                topics=topics,
                topic_contexts=topic_contexts,
                proficiency=proficiency,
                refine=True,
            )
            logger.info("Pipeline: %d chars (source=%s)", len(fused_note or ""), source)
        except Exception as exc:
            pipe_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Pipeline generation failed: %s", pipe_error)

    if not fused_note or len(fused_note.strip()) < 100:
        logger.info("Falling back to local summarizer")
        fused_note = generate_local_note(all_slides_text, all_textbook_text, proficiency)
        source     = "local"

    from pipeline.note_generator import _fix_tables
    fused_note = fix_latex_delimiters(_fix_tables(fused_note))

    if fused_note and topic_figures:
        fused_note = _inject_figures_into_sections(fused_note, topic_figures)

    # ── Store note pages ──────────────────────────────────────────────────────
    if notebook_id:
        try:
            pages = _note_to_pages(fused_note)
            store_note_pages(notebook_id, pages)
            logger.info("Stored %d pages for %s", len(pages), notebook_id)
        except Exception as e:
            logger.warning("Note page store failed: %s", e)
        try:
            update_notebook_note(notebook_id, fused_note, proficiency)
        except Exception:
            pass

    fallback_warning = None
    if source == "local" and pipe_error:
        fallback_warning = f"AI unavailable ({pipe_error}) — offline notes used."
    elif source == "local":
        fallback_warning = "No AI configured — offline summariser used."

    return FusionResponse(
        fused_note=fused_note,
        source=source,
        fallback_reason=fallback_warning,
        chunks_stored=chunks_stored,
    )


# ── Image serving ──────────────────────────────────────────────────────────────

@app.get("/api/images/{notebook_id}/{img_filename}")
async def serve_slide_image(notebook_id: str, img_filename: str):
    # FIX (round 4): reject path-traversal attempts in both path segments.
    # <img> tags cannot send Authorization headers, so Bearer auth is not
    # practical here; path hardening prevents directory escape instead.
    import re as _re
    if not _re.fullmatch(r'[a-zA-Z0-9_\-]+', notebook_id) or \
       not _re.fullmatch(r'[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+', img_filename):
        raise HTTPException(400, "Invalid image path")
    path = get_image_path(notebook_id, img_filename)
    if not path:
        raise HTTPException(404, f"Image {img_filename} not found")
    ext  = img_filename.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/png")
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "max-age=3600"})


# ── Backward-compat single-file upload ────────────────────────────────────────

@app.post("/api/upload-fuse", response_model=FusionResponse)
async def upload_fuse(
    slides_pdf:   UploadFile = File(...),
    textbook_pdf: UploadFile = File(...),
    proficiency:  str = Form("Practitioner"),
    notebook_id:  str = Form(""),
    authorization: Optional[str] = Header(None),
):
    # FIX: require auth on backward-compat endpoint too
    get_current_user(authorization)
    slides_pdf.filename   = slides_pdf.filename   or "slides.pdf"
    textbook_pdf.filename = textbook_pdf.filename or "textbook.pdf"
    return await upload_fuse_multi(
        slides_pdfs=[slides_pdf], textbook_pdfs=[textbook_pdf],
        proficiency=proficiency, notebook_id=notebook_id,
        authorization=authorization,
    )


# ── Doubt answering (FIX A3: auth required) ───────────────────────────────────

@app.post("/api/doubt", response_model=DoubtResponse)
async def answer_doubt(
    req: DoubtRequest,
    authorization: Optional[str] = Header(None),
):
    """FIX A3: Bearer token required."""
    get_current_user(authorization)

    slide_hits    = retrieve_relevant_chunks(req.notebook_id, req.doubt, top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(req.notebook_id, req.doubt, top_k=6, source_filter="textbook")
    slide_ctx    = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_ctx = _format_chunks_for_prompt(textbook_hits, 8_000)
    note_page    = get_note_page(req.notebook_id, req.page_idx) or ""

    if _is_azure_available():
        try:
            answer = await fusion_agent.answer_doubt(
                doubt=req.doubt, slide_context=slide_ctx,
                textbook_context=textbook_ctx, note_page=note_page,
            )
            return DoubtResponse(answer=fix_latex_delimiters(answer), source="azure")
        except Exception as e:
            logger.warning("Azure doubt failed: %s", e)

    if _is_groq_available():
        try:
            answer = await _groq_doubt(req.doubt, slide_ctx, textbook_ctx, note_page)
            return DoubtResponse(answer=fix_latex_delimiters(answer), source="groq")
        except Exception as e:
            logger.warning("Groq doubt failed: %s", e)

    from agents.local_mutation import _diagnose_gap, _build_analogy_hint
    gap     = _diagnose_gap(req.doubt)
    analogy = _build_analogy_hint(req.doubt)
    answer  = f"**{gap}**\n\n{analogy}"
    if note_page:
        answer += f"\n\n*From your notes:* {note_page[:300]}…"
    return DoubtResponse(answer=fix_latex_delimiters(answer), source="local")


# ── Mutation (FIX A4, A7, L3: auth + dynamic concept + single parser) ─────────

@app.post("/api/mutate", response_model=MutationResponse)
async def mutate_note(
    req: MutationRequest,
    authorization: Optional[str] = Header(None),
):
    """
    FIX A4: Bearer token required.
    FIX A7: No hardcoded "Convolution Theorem" — extracts real concept from note.
    FIX L3: Single mutate parser via FusionAgent._parse_mutate_response.
    """
    user = get_current_user(authorization)  # FIX A4
    _username = user.get("username", "anonymous")

    note_page = get_note_page(req.notebook_id, req.page_idx)
    if note_page is None:
        note_page = req.original_paragraph or ""

    query = req.doubt + " " + note_page[:200]
    slide_hits    = retrieve_relevant_chunks(req.notebook_id, query, top_k=6, source_filter="slides")
    textbook_hits = retrieve_relevant_chunks(req.notebook_id, query, top_k=6, source_filter="textbook")
    slide_ctx    = _format_chunks_for_prompt(slide_hits,    8_000)
    textbook_ctx = _format_chunks_for_prompt(textbook_hits, 8_000)

    mutated, gap, llm_source = await _llm_mutate(note_page, req.doubt, slide_ctx, textbook_ctx)

    if mutated is None:
        mutated, gap = local_mutate(note_page, req.doubt)
        llm_source   = "local"

    can_mutate = llm_source in ("azure", "groq")

    from pipeline.note_generator import _fix_tables
    mutated = fix_latex_delimiters(_fix_tables(mutated))

    if can_mutate and req.notebook_id:
        try:
            updated = update_note_page(req.notebook_id, req.page_idx, mutated)
            if updated:
                full_note = "\n\n".join(get_all_note_pages(req.notebook_id))
                update_notebook_note(req.notebook_id, full_note)
                logger.info("Mutated page %d for %s", req.page_idx, req.notebook_id)
        except Exception as e:
            logger.warning("Page update failed: %s", e)

    # FIX A7: dynamically extract real concept from the mutated note section
    if req.notebook_id and mutated:
        try:
            graph = extract_concepts(mutated)
            if graph.get("nodes"):
                top_concept = graph["nodes"][0]["label"]
                update_node_status(top_concept, "partial", _username)
        except Exception:
            pass   # non-critical — don't break mutation over graph update failure

    return MutationResponse(
        mutated_paragraph=mutated,
        concept_gap=gap or "Student required additional clarification.",
        page_idx=req.page_idx,
        source=llm_source,
        can_mutate=can_mutate,
    )


# ── Examiner (FIX A5: auth required) ─────────────────────────────────────────

@app.post("/api/examine", response_model=ExaminerResponse)
async def examine_concept(
    req: ExaminerRequest,
    authorization: Optional[str] = Header(None),
):
    """FIX A5: Bearer token required to prevent free LLM abuse."""
    get_current_user(authorization)

    if examiner_agent and _is_azure_available():
        try:
            q = await examiner_agent.examine(req.concept_name)
            return ExaminerResponse(practice_questions=fix_latex_delimiters(q))
        except Exception as e:
            logger.warning("Azure examiner failed: %s", e)
    if _is_groq_available():
        try:
            q = await _groq_examine(req.concept_name)
            return ExaminerResponse(practice_questions=fix_latex_delimiters(q))
        except Exception as e:
            logger.warning("Groq examiner failed: %s", e)
    q = local_examine(req.concept_name)
    return ExaminerResponse(practice_questions=fix_latex_delimiters(q))


# ── Graph routes (FIX A2: auth required) ──────────────────────────────────────

@app.get("/api/graph")
async def get_graph(authorization: Optional[str] = Header(None)):
    """FIX A2: requires Bearer token."""
    user = get_current_user(authorization)
    return get_db(user.get("username", "anonymous"))


@app.post("/api/graph/update")
async def update_graph(
    req: NodeUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    user = get_current_user(authorization)
    updated = update_node_status(req.concept_name, req.status, user.get("username", "anonymous"))
    if not updated:
        raise HTTPException(404, "Node not found")
    return {"status": "success", "node": updated}


@app.post("/api/extract-concepts")
async def extract_concepts_endpoint(
    req: ConceptExtractRequest,
    authorization: Optional[str] = Header(None),
):
    user = get_current_user(authorization)
    graph = extract_concepts(req.note)
    if req.notebook_id:
        # FIX: verify ownership before writing the graph — prevents a user from
        # overwriting another user's notebook graph with their own note text.
        try:
            _require_notebook_owner(req.notebook_id, user)
            update_notebook_graph(req.notebook_id, graph)
        except HTTPException:
            pass   # notebook not owned by this user — return graph but don't save
    return graph


@app.get("/notebooks/{nb_id}/graph")
async def get_notebook_graph(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb   = _require_notebook_owner(nb_id, user)
    return nb.get("graph", {"nodes": [], "edges": []})


@app.post("/notebooks/{nb_id}/graph/update")
async def update_notebook_graph_node(
    nb_id: str,
    req: NodeUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    user  = get_current_user(authorization)
    nb    = _require_notebook_owner(nb_id, user)
    graph = nb.get("graph", {"nodes": [], "edges": []})
    for node in graph["nodes"]:
        if node["label"].lower() == req.concept_name.lower():
            node["status"] = req.status
            update_notebook_graph(nb_id, graph)
            return {"status": "success", "node": node}
    raise HTTPException(404, "Concept node not found")


# ── Legacy /api/fuse (FIX L1 + L4) ───────────────────────────────────────────

class FusionRequest(BaseModel):
    slide_summary:      str
    textbook_paragraph: str
    proficiency:        str = "Practitioner"
    notebook_id:        Optional[str] = None


@app.post("/api/fuse", response_model=FusionResponse)
async def fuse_knowledge(req: FusionRequest, authorization: Optional[str] = Header(None)):
    """
    Legacy text-based fusion.
    FIX: require auth to prevent anonymous LLM abuse.
    FIX L1: now stores source chunks so /api/doubt and /api/mutate work.
    FIX L4: now uses run_generation_pipeline (same path as upload-fuse-multi).
    """
    get_current_user(authorization)
    from pipeline.chunker import chunk_textbook
    from pipeline.embedder import Embedder
    from pipeline.vector_db import VectorDB
    from pipeline.slide_analyzer import analyse_slides
    from pipeline.topic_retriever import TopicRetriever
    from pipeline.note_generator import run_generation_pipeline

    slide_content    = req.slide_summary[:_PROMPT_SLIDES_BUDGET]
    textbook_content = req.textbook_paragraph[:_PROMPT_TEXTBOOK_BUDGET]
    nb_id            = req.notebook_id

    # FIX L1: store raw chunks for doubt/mutate
    if nb_id:
        try:
            tb_hash = hashlib.md5(textbook_content.encode()).hexdigest()[:16]
            store_source_chunks(
                nb_id=nb_id,
                slide_chunks=chunk_text(slide_content,    max_chars=4000),
                textbook_chunks=chunk_text(textbook_content, max_chars=4000),
                textbook_hash=tb_hash,
            )
        except Exception as e:
            logger.warning("/api/fuse: chunk store failed: %s", e)

    # FIX L4: run same pipeline as upload-fuse-multi
    fused_note, source = None, "local"
    try:
        topics = await analyse_slides(slide_content)
        if topics:
            embedder  = Embedder()
            vector_db = VectorDB()
            tb_chunks = chunk_textbook(textbook_content) if textbook_content.strip() else []
            if tb_chunks:
                embedder.embed_chunks(tb_chunks)
                vector_db.add_chunks(tb_chunks)
            topic_contexts: dict[str, str] = {}
            if vector_db.size > 0:
                retriever     = TopicRetriever(vector_db, embedder)
                topic_contexts = retriever.retrieve_all_topics(topics)
            fused_note, source = await run_generation_pipeline(
                topics=topics,
                topic_contexts=topic_contexts,
                proficiency=req.proficiency,
                refine=True,
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
