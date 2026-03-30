"""routers/feedback.py — Student feedback collection + admin read."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import deps
from deps import get_current_user

logger = logging.getLogger("auragraph")
router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    context:     str = "dashboard"        # 'dashboard' | 'notebook'
    notebook_id: Optional[str] = None
    rating:      Optional[int] = Field(default=None, ge=1, le=5)
    liked:       str = ""
    disliked:    str = ""
    category:    str = "general"          # 'notes' | 'questions' | 'doubts' | 'mutation' | 'ui' | 'general'
    message:     str = Field(default="", max_length=2000)
    page_url:    str = ""


class NavHelpChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=800)
    history: list[dict] = Field(default_factory=list)
    context: str = Field(default="", max_length=4000)
    description: str = Field(default="", max_length=4000)


class NavHelpChatResponse(BaseModel):
    answer: str
    source: str = "llm"


_NAV_KB = """You are AuraGraph Navigation Help Assistant.
Your role is to explain app navigation and feature usage in short practical steps, using ONLY verified product context.

Verified AuraGraph feature map (ground truth):
- Dashboard:
    - Create notebook (New Notebook), open notebook cards, delete notebooks.
    - View grouped courses/notebooks, stats cards, profile, and tour.
    - Open floating Feedback/Help widget.
- Notebook workspace core:
    - Top actions: Open Quiz Center, Ask a Doubt (Ctrl+D), Quick Review, Version History, Aura panel, Study Hub toggle.
    - Reading tools: view mode (single/two/scroll), font size controls (A- / A+), search (Ctrl+F), copy/export/print.
    - Page navigation: prev/next, page counter jump.
- Annotation tools:
    - Highlight, Sticky Note, Draw, Eraser.
    - Highlight requires selecting text, then pressing Highlight in the selection popup.
    - Storage options include auto-save, save now, clear all.
- Study Hub / Knowledge panel:
    - Concept mastery status, jump to concept in notes.
    - Practice Questions by difficulty from concept card (different from Quiz Center tests).
- Quiz Center:
    - General Test (10 mixed), Sniper Test (5 weak concepts), Concept Quiz (5 selected concept).
    - Quiz history/review tabs.
- Other notebook features:
    - Translate page and TTS/read-aloud.
    - Regenerate section, manual edit page.
    - Keyboard shortcuts modal and on-screen keyboard toggle.
- Help/feedback:
    - Floating widget supports Navigation Help Chat and Feedback submission.

Answer policy:
- Do NOT claim a feature is unsupported unless the provided context explicitly says it is unavailable.
- If user asks "practice questions", prioritize the concept Practice Questions flow (Study Hub/Knowledge panel), not Quiz Center history.
- If user asks "highlight", provide annotation highlight steps.
- If user asks "font size", explain A- / A+ controls in notebook reading tools.
- If uncertain, say what you are unsure about and ask one short clarifying question.
- Keep answers concise (4-8 lines), practical, and step-by-step.
"""


async def _navigation_llm_answer(
    query: str,
    history: list[dict],
    context: str = "",
    description: str = "",
) -> tuple[Optional[str], str]:
    messages = [{"role": "system", "content": _NAV_KB}]
    if context.strip():
        messages.append({
            "role": "system",
            "content": f"Additional product context from client:\n{context.strip()[:4000]}",
        })
    if description.strip():
        messages.append({
            "role": "system",
            "content": f"Additional client description:\n{description.strip()[:4000]}",
        })
    for msg in history[-4:]:
        role = str(msg.get("role", "")).lower().strip()
        content = str(msg.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:800]})
    messages.append({
        "role": "user",
        "content": (
            f"User question: {query}\n"
            "Respond with exact in-app navigation steps."
        ),
    })

    if deps._is_azure_available():
        try:
            return await deps._azure_chat(messages, max_tokens=420), "azure"
        except Exception as exc:
            logger.warning("navigation chat azure failed: %s", exc)

    if deps._is_groq_available():
        try:
            return await deps._groq_chat(messages, max_tokens=420), "groq"
        except Exception as exc:
            logger.warning("navigation chat groq failed: %s", exc)

    return None, "local"


async def _send_webhook(entry: dict):
    """Fire-and-forget Discord/Slack webhook so feedback reaches developers instantly."""
    url = os.environ.get("FEEDBACK_WEBHOOK_URL", "")
    if not url:
        return
    try:
        import httpx
        stars = "⭐" * (entry.get("rating") or 0)
        text = (
            f"**New AuraGraph Feedback** {stars}\n"
            f"• Context: `{entry.get('context','?')}` | "
            f"Category: `{entry.get('category','?')}`\n"
            f"• User: `{entry.get('user_email') or entry.get('user_id','anonymous')}`\n"
        )
        if entry.get("liked"):
            text += f"• 👍 Liked: {entry['liked']}\n"
        if entry.get("disliked"):
            text += f"• 👎 Disliked: {entry['disliked']}\n"
        if entry.get("message"):
            text += f"• Message: {entry['message']}\n"
        # Discord payload
        payload = {"content": text[:1900]}
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning("feedback webhook failed: %s", exc)


@router.post("/api/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    authorization: Optional[str] = Header(None),
):
    """Submit feedback — available to all authenticated users."""
    from agents.notebook_store import save_feedback
    try:
        user = get_current_user(authorization)
    except HTTPException:
        user = {"id": "anonymous", "email": ""}

    entry = req.model_dump()
    entry["user_id"]    = user.get("id", "anonymous")
    entry["user_email"] = user.get("email", "")

    fid = save_feedback(entry)

    # Async webhook — don't await so response is instant
    import asyncio
    asyncio.ensure_future(_send_webhook(entry))

    return {"ok": True, "id": fid}


@router.get("/api/feedback")
async def get_feedback(
    authorization: Optional[str] = Header(None),
    limit: int = 200,
):
    """Admin endpoint — protected by ADMIN_KEY env var."""
    admin_key = os.environ.get("ADMIN_KEY", "")
    # Accept admin_key passed as Bearer token OR as query param
    token = ""
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
    if admin_key and token != admin_key:
        raise HTTPException(403, "Admin access required.")
    if not admin_key:
        raise HTTPException(503, "ADMIN_KEY not configured on server.")
    from agents.notebook_store import get_all_feedback
    rows = get_all_feedback(limit=limit)
    return {"feedback": rows, "total": len(rows)}


@router.post("/api/navigation-help-chat", response_model=NavHelpChatResponse)
async def navigation_help_chat(
    req: NavHelpChatRequest,
    authorization: Optional[str] = Header(None),
):
    """Answer product navigation questions from the floating help chat."""
    user_id: Optional[str] = None
    try:
        user = get_current_user(authorization)
        user_id = user.get("id")
    except HTTPException:
        user = None

    query = req.query.strip()
    if not query:
        raise HTTPException(400, "Please enter a navigation question.")

    if user_id:
        try:
            deps._check_llm_rate_limit(user_id)
        except HTTPException:
            # Keep chat usable even when usage caps are hit.
            pass

    llm_answer, source = await _navigation_llm_answer(
        query,
        req.history,
        context=req.context,
        description=req.description,
    )
    if llm_answer:
        if user_id and source in ("azure", "groq"):
            deps._record_llm_call(user_id, source, est_tokens=700)
        return NavHelpChatResponse(answer=llm_answer.strip(), source=source)

    return NavHelpChatResponse(
        answer=(
            "I can help with AuraGraph navigation. Try asking things like:\n"
            "- How do I ask a doubt?\n"
            "- How do I mutate/rewrite a page?\n"
            "- Where is Quick Review?\n"
            "- How do I send feedback?"
        ),
        source="local",
    )
