"""
AuraGraph - FastAPI + Semantic Kernel Backend
Team: Wowffulls | IIT Roorkee | Challenge: AI Study Buddy
"""

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
from agents.mutation_agent import MutationAgent
from agents.examiner_agent import ExaminerAgent
from agents.mock_cosmos import get_db, update_node_status
from agents.pdf_utils import extract_text_from_pdf, summarise_chunks, chunk_text
from agents.local_summarizer import generate_local_note
from agents.local_mutation import local_mutate
from agents.local_examiner import local_examine
from agents.concept_extractor import extract_concepts
from agents.auth_utils import register_user, login_user, validate_token
from agents.notebook_store import (
    create_notebook, get_notebooks, get_notebook,
    update_notebook_note, update_notebook_graph, delete_notebook
)

load_dotenv()

# ---------------------------------------------------------------------------
# Kernel Singleton
# ---------------------------------------------------------------------------
kernel = None
fusion_agent = None
mutation_agent = None
examiner_agent = None


@asynccontextmanager
async def lifespan(app):
    global kernel, fusion_agent, mutation_agent, examiner_agent

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
    mutation_agent = MutationAgent(kernel)
    examiner_agent = ExaminerAgent(kernel)

    print("✅  AuraGraph – Azure OpenAI kernel ready")
    yield
    print("⏹  AuraGraph shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AuraGraph API",
    version="0.2.0",
    description="Digital Knowledge Twin – Multi-Notebook, Auth + Knowledge Fusion",
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    token = authorization.split(" ", 1)[1]
    user = validate_token(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AuthRequest(BaseModel):
    email: str
    password: str

class FusionRequest(BaseModel):
    slide_summary: str
    textbook_paragraph: str
    proficiency: str = "Intermediate"

class FusionResponse(BaseModel):
    fused_note: str

class MutationRequest(BaseModel):
    original_paragraph: str
    student_doubt: str

class MutationResponse(BaseModel):
    mutated_paragraph: str
    concept_gap: str

class ExaminerRequest(BaseModel):
    concept_name: str

class ExaminerResponse(BaseModel):
    practice_questions: str

class NodeUpdateRequest(BaseModel):
    concept_name: str
    status: str


class ConceptExtractRequest(BaseModel):
    note: str
    notebook_id: Optional[str] = None

class NotebookCreateRequest(BaseModel):
    name: str
    course: str

class NotebookUpdateRequest(BaseModel):
    note: str
    proficiency: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "AuraGraph v0.2"}


@app.post("/auth/register")
async def auth_register(req: AuthRequest):
    user = register_user(req.email, req.password)
    if not user:
        raise HTTPException(409, "Email already registered")
    return user


@app.post("/auth/login")
async def auth_login(req: AuthRequest):
    user = login_user(req.email, req.password)
    if not user:
        raise HTTPException(401, "Invalid email or password")
    return user


# ---------------------------------------------------------------------------
# Notebook Routes
# ---------------------------------------------------------------------------
@app.post("/notebooks")
async def new_notebook(req: NotebookCreateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb = create_notebook(user["id"], req.name, req.course)
    return nb


@app.get("/notebooks")
async def list_notebooks(authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    return get_notebooks(user["id"])


@app.get("/notebooks/{nb_id}")
async def fetch_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb = get_notebook(nb_id)
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    return nb


@app.patch("/notebooks/{nb_id}/note")
async def save_notebook_note(nb_id: str, req: NotebookUpdateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb = get_notebook(nb_id)
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    updated = update_notebook_note(nb_id, req.note, req.proficiency)
    return updated


@app.delete("/notebooks/{nb_id}")
async def remove_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    nb = get_notebook(nb_id)
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    delete_notebook(nb_id)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# AI Routes
# ---------------------------------------------------------------------------
@app.post("/api/fuse", response_model=FusionResponse)
async def fuse_knowledge(req: FusionRequest):
    if not fusion_agent:
        raise HTTPException(503, "Kernel not initialised")
    fused = await fusion_agent.fuse(req.slide_summary, req.textbook_paragraph, req.proficiency)
    return FusionResponse(fused_note=fused)


@app.post("/api/upload-fuse", response_model=FusionResponse)
async def upload_fuse(
    slides_pdf: UploadFile = File(...),
    textbook_pdf: UploadFile = File(...),
    proficiency: str = Form("Intermediate"),
):
    if not fusion_agent:
        raise HTTPException(503, "Kernel not initialised")

    slides_bytes = await slides_pdf.read()
    textbook_bytes = await textbook_pdf.read()

    try:
        slides_text = extract_text_from_pdf(slides_bytes)
        textbook_text = extract_text_from_pdf(textbook_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))

    slides_summary = summarise_chunks(chunk_text(slides_text), max_summary_chars=6000)
    textbook_summary = summarise_chunks(chunk_text(textbook_text), max_summary_chars=6000)

    fused = await fusion_agent.fuse(slides_summary, textbook_summary, proficiency)
    return FusionResponse(fused_note=fused)


@app.post("/api/upload-fuse-multi", response_model=FusionResponse)
async def upload_fuse_multi(
    slides_pdfs: List[UploadFile] = File(...),
    textbook_pdfs: List[UploadFile] = File(...),
    proficiency: str = Form("Intermediate"),
):
    """
    Multi-file Fusion Endpoint
    Accepts any number of slide PDFs and textbook PDFs.
    Tries Azure OpenAI fusion first; falls back to local extractive summarizer.
    """
    # Extract and concatenate text from all slide files
    all_slides_text = ""
    for upload in slides_pdfs:
        raw = await upload.read()
        try:
            all_slides_text += extract_text_from_pdf(raw) + "\n\n"
        except ValueError:
            pass

    # Extract and concatenate text from all textbook files
    all_textbook_text = ""
    for upload in textbook_pdfs:
        raw = await upload.read()
        try:
            all_textbook_text += extract_text_from_pdf(raw) + "\n\n"
        except ValueError:
            pass

    if not all_slides_text.strip() and not all_textbook_text.strip():
        raise HTTPException(422, "Could not extract text from any uploaded PDFs.")

    # 1) Try Azure OpenAI fusion
    if fusion_agent:
        try:
            slides_summary = summarise_chunks(chunk_text(all_slides_text), max_summary_chars=10000)
            textbook_summary = summarise_chunks(chunk_text(all_textbook_text), max_summary_chars=10000)
            fused = await fusion_agent.fuse(slides_summary, textbook_summary, proficiency)
            return FusionResponse(fused_note=fused)
        except Exception:
            pass  # Fall through to local summarizer

    # 2) Local extractive summarizer fallback (works without any API key)
    local_note = generate_local_note(all_slides_text, all_textbook_text, proficiency)
    return FusionResponse(fused_note=local_note)




@app.post("/api/mutate", response_model=MutationResponse)
async def mutate_note(req: MutationRequest):
    if mutation_agent:
        try:
            mutated, gap = await mutation_agent.mutate(req.original_paragraph, req.student_doubt)
            update_node_status("Convolution Theorem", "partial")
            return MutationResponse(mutated_paragraph=mutated, concept_gap=gap)
        except Exception:
            pass  # fall through to local fallback
    # Local offline fallback
    mutated, gap = local_mutate(req.original_paragraph, req.student_doubt)
    return MutationResponse(mutated_paragraph=mutated, concept_gap=gap)


@app.post("/api/examine", response_model=ExaminerResponse)
async def examine_concept(req: ExaminerRequest):
    if examiner_agent:
        try:
            questions = await examiner_agent.examine(req.concept_name)
            return ExaminerResponse(practice_questions=questions)
        except Exception:
            pass  # fall through to local fallback
    # Local offline fallback
    questions = local_examine(req.concept_name)
    return ExaminerResponse(practice_questions=questions)


@app.get("/api/graph")
async def get_graph():
    return get_db()


@app.post("/api/graph/update")
async def update_graph(req: NodeUpdateRequest):
    updated_node = update_node_status(req.concept_name, req.status)
    if not updated_node:
        raise HTTPException(404, "Node not found")
    return {"status": "success", "node": updated_node}


@app.post("/api/extract-concepts")
async def extract_concepts_endpoint(req: ConceptExtractRequest):
    """Extract concept graph nodes from a fused note."""
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
    authorization: Optional[str] = Header(None)
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
