"""
AuraGraph - FastAPI Backend
Team: Wowffulls | IIT Roorkee | AI Study Buddy
"""
import os
import uuid
import hashlib
import time
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Header
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, List
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from agents.pdf_utils import extract_text_from_pdf, summarise_chunks, chunk_text
from agents.local_summarizer import generate_local_note
from agents.local_mutation import local_mutate
from agents.local_examiner import local_examine
from agents.concept_extractor import extract_concepts
from agents.ai_agents import ai_fuse, ai_mutate, ai_examine, fix_latex_delimiters

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

TOKEN_TTL_SECONDS = 7 * 24 * 3600


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="AuraGraph API", version="1.0.0")
api_router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AuthRequest(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str

    @property
    def identifier(self) -> str:
        return (self.email or self.username or "").strip()


class NotebookCreateRequest(BaseModel):
    name: str
    course: str


class NotebookUpdateRequest(BaseModel):
    note: str
    proficiency: Optional[str] = None


class FusionRequest(BaseModel):
    slide_summary: str
    textbook_paragraph: str
    proficiency: str = "Intermediate"


class MutationRequest(BaseModel):
    original_paragraph: str
    student_doubt: str


class ExaminerRequest(BaseModel):
    concept_name: str


class NodeUpdateRequest(BaseModel):
    concept_name: str
    status: str


class ConceptExtractRequest(BaseModel):
    note: str
    notebook_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


_DEMO_USER = {
    "id": "demo",
    "email": "demo@auragraph.local",
    "name": "Demo",
    "token": "demo-token",
}


async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    token = authorization.split(" ", 1)[1]
    if token == "demo-token":
        return dict(_DEMO_USER)
    user = await db.users.find_one({"token": token}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    issued_at = user.get("token_issued_at", 0)
    if time.time() - issued_at > TOKEN_TTL_SECONDS:
        raise HTTPException(401, "Token expired")
    return user


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------
@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "AuraGraph v1.0"}


@api_router.post("/auth/register")
async def auth_register(req: AuthRequest):
    identifier = req.identifier
    if not identifier:
        raise HTTPException(422, "email or username is required")
    existing = await db.users.find_one({"email": identifier})
    if existing:
        raise HTTPException(409, "Account already exists")
    user = {
        "id": str(uuid.uuid4()),
        "email": identifier,
        "password_hash": _hash_password(req.password),
        "token": str(uuid.uuid4()),
        "token_issued_at": time.time(),
        "name": identifier.split("@")[0].capitalize(),
    }
    await db.users.insert_one({**user})
    return {k: v for k, v in user.items() if k not in ("password_hash", "_id")}


@api_router.post("/auth/login")
async def auth_login(req: AuthRequest):
    identifier = req.identifier
    if not identifier:
        raise HTTPException(422, "email or username is required")
    ph = _hash_password(req.password)
    user = await db.users.find_one({"email": identifier, "password_hash": ph})
    if not user:
        raise HTTPException(401, "Invalid credentials")
    new_token = str(uuid.uuid4())
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"token": new_token, "token_issued_at": time.time()}})
    user["token"] = new_token
    return {k: v for k, v in user.items() if k not in ("password_hash", "_id")}


# ---------------------------------------------------------------------------
# Notebook Routes
# ---------------------------------------------------------------------------
@api_router.post("/notebooks")
async def new_notebook(req: NotebookCreateRequest, authorization: Optional[str] = Header(None)):
    user = await get_current_user(authorization)
    nb = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "name": req.name,
        "course": req.course,
        "note": "",
        "proficiency": "Intermediate",
        "graph": {"nodes": [], "edges": []},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notebooks.insert_one({**nb})
    return {k: v for k, v in nb.items() if k != "_id"}


@api_router.get("/notebooks")
async def list_notebooks(authorization: Optional[str] = Header(None)):
    user = await get_current_user(authorization)
    notebooks = await db.notebooks.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return notebooks


@api_router.get("/notebooks/{nb_id}")
async def fetch_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = await get_current_user(authorization)
    nb = await db.notebooks.find_one({"id": nb_id}, {"_id": 0})
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    return nb


@api_router.patch("/notebooks/{nb_id}/note")
async def save_notebook_note(nb_id: str, req: NotebookUpdateRequest, authorization: Optional[str] = Header(None)):
    user = await get_current_user(authorization)
    nb = await db.notebooks.find_one({"id": nb_id})
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    update = {"note": req.note, "updated_at": datetime.now(timezone.utc).isoformat()}
    if req.proficiency:
        update["proficiency"] = req.proficiency
    await db.notebooks.update_one({"id": nb_id}, {"$set": update})
    nb.update(update)
    return {k: v for k, v in nb.items() if k != "_id"}


@api_router.delete("/notebooks/{nb_id}")
async def remove_notebook(nb_id: str, authorization: Optional[str] = Header(None)):
    user = await get_current_user(authorization)
    nb = await db.notebooks.find_one({"id": nb_id})
    if not nb or nb["user_id"] != user["id"]:
        raise HTTPException(404, "Notebook not found")
    await db.notebooks.delete_one({"id": nb_id})
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# AI Routes
# ---------------------------------------------------------------------------
@api_router.post("/fuse")
async def fuse_knowledge(req: FusionRequest):
    try:
        fused = await ai_fuse(req.slide_summary, req.textbook_paragraph, req.proficiency)
        return {"fused_note": fused}
    except Exception as e:
        logger.warning(f"AI fusion failed, using local: {e}")
        local_note = generate_local_note(req.slide_summary, req.textbook_paragraph, req.proficiency)
        return {"fused_note": fix_latex_delimiters(local_note)}


@api_router.post("/upload-fuse")
async def upload_fuse(
    slides_pdf: UploadFile = File(...),
    textbook_pdf: UploadFile = File(...),
    proficiency: str = Form("Intermediate"),
):
    slides_bytes = await slides_pdf.read()
    textbook_bytes = await textbook_pdf.read()
    try:
        slides_text = extract_text_from_pdf(slides_bytes)
        textbook_text = extract_text_from_pdf(textbook_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))

    slides_summary = summarise_chunks(chunk_text(slides_text), max_summary_chars=6000)
    textbook_summary = summarise_chunks(chunk_text(textbook_text), max_summary_chars=6000)

    try:
        fused = await ai_fuse(slides_summary, textbook_summary, proficiency)
        return {"fused_note": fused}
    except Exception as e:
        logger.warning(f"AI fusion failed, using local: {e}")
        local_note = generate_local_note(slides_text, textbook_text, proficiency)
        return {"fused_note": fix_latex_delimiters(local_note)}


@api_router.post("/upload-fuse-multi")
async def upload_fuse_multi(
    slides_pdfs: List[UploadFile] = File(...),
    textbook_pdfs: List[UploadFile] = File(...),
    proficiency: str = Form("Intermediate"),
):
    all_slides_text = ""
    for upload in slides_pdfs:
        raw = await upload.read()
        try:
            all_slides_text += extract_text_from_pdf(raw) + "\n\n"
        except ValueError:
            pass

    all_textbook_text = ""
    for upload in textbook_pdfs:
        raw = await upload.read()
        try:
            all_textbook_text += extract_text_from_pdf(raw) + "\n\n"
        except ValueError:
            pass

    if not all_slides_text.strip() and not all_textbook_text.strip():
        raise HTTPException(422, "Could not extract text from any uploaded PDFs.")

    try:
        slides_summary = summarise_chunks(chunk_text(all_slides_text), max_summary_chars=10000)
        textbook_summary = summarise_chunks(chunk_text(all_textbook_text), max_summary_chars=10000)
        fused = await ai_fuse(slides_summary, textbook_summary, proficiency)
        return {"fused_note": fused}
    except Exception as e:
        logger.warning(f"AI fusion failed, using local: {e}")
        local_note = generate_local_note(all_slides_text, all_textbook_text, proficiency)
        return {"fused_note": fix_latex_delimiters(local_note)}


@api_router.post("/mutate")
async def mutate_note(req: MutationRequest):
    try:
        mutated, gap = await ai_mutate(req.original_paragraph, req.student_doubt)
        return {"mutated_paragraph": mutated, "concept_gap": gap}
    except Exception as e:
        logger.warning(f"AI mutation failed, using local: {e}")
        mutated, gap = local_mutate(req.original_paragraph, req.student_doubt)
        return {"mutated_paragraph": fix_latex_delimiters(mutated), "concept_gap": gap}


@api_router.post("/examine")
async def examine_concept(req: ExaminerRequest):
    try:
        questions = await ai_examine(req.concept_name)
        return {"practice_questions": questions}
    except Exception as e:
        logger.warning(f"AI examiner failed, using local: {e}")
        questions = local_examine(req.concept_name)
        return {"practice_questions": questions}


@api_router.post("/extract-concepts")
async def extract_concepts_endpoint(req: ConceptExtractRequest):
    graph = extract_concepts(req.note)
    if req.notebook_id:
        await db.notebooks.update_one(
            {"id": req.notebook_id},
            {"$set": {"graph": graph, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    return graph


@api_router.get("/notebooks/{nb_id}/graph")
async def get_notebook_graph(nb_id: str, authorization: Optional[str] = Header(None)):
    nb = await db.notebooks.find_one({"id": nb_id}, {"_id": 0})
    if not nb:
        raise HTTPException(404, "Notebook not found")
    return nb.get("graph", {"nodes": [], "edges": []})


@api_router.post("/notebooks/{nb_id}/graph/update")
async def update_notebook_graph_node(nb_id: str, req: NodeUpdateRequest, authorization: Optional[str] = Header(None)):
    nb = await db.notebooks.find_one({"id": nb_id})
    if not nb:
        raise HTTPException(404, "Notebook not found")
    graph = nb.get("graph", {"nodes": [], "edges": []})
    for node in graph["nodes"]:
        if node["label"].lower() == req.concept_name.lower():
            node["status"] = req.status
            await db.notebooks.update_one({"id": nb_id}, {"$set": {"graph": graph}})
            return {"status": "success", "node": node}
    raise HTTPException(404, "Concept node not found")


# ---------------------------------------------------------------------------
# Include router & middleware
# ---------------------------------------------------------------------------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
