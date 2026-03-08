"""
AuraGraph — FastAPI Backend  v6
Team: Wowffulls | IIT Roorkee | Challenge: AI Study Buddy

main.py is intentionally thin: app wiring + middleware + lifespan + health/usage.
All business logic lives in routers/ and deps.py.
"""
import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()

logger = logging.getLogger("auragraph")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")


# ── Lifespan: boot global agents + write-lock ──────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    import semantic_kernel as sk
    from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
    from agents.fusion_agent import FusionAgent
    from agents.examiner_agent import ExaminerAgent
    import deps

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

    deps.kernel         = kernel
    deps.fusion_agent   = FusionAgent(kernel)
    deps.examiner_agent = ExaminerAgent(kernel)
    deps._db_write_lock = asyncio.Lock()

    deps._init_usage_table()
    logger.info("✅  AuraGraph v6 — bcrypt auth, SQLite mastery store, LLM rate limiting")
    yield
    logger.info("⏹  AuraGraph shutting down")


# ── App + middleware ───────────────────────────────────────────────────────────

app = FastAPI(
    title="AuraGraph API",
    version="0.6.0",
    description="Digital Knowledge Twin — modular v6",
    lifespan=lifespan,
)

_CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id   = str(uuid.uuid4())[:8]
        request.state.request_id = req_id
        t0       = time.perf_counter()
        response = await call_next(request)
        ms       = (time.perf_counter() - t0) * 1000
        response.headers["X-Request-Id"] = req_id
        logger.info("[%s] %s %s -> %d  %.1fms",
                    req_id, request.method, request.url.path, response.status_code, ms)
        return response


app.add_middleware(_RequestIdMiddleware)


# ── Routers ────────────────────────────────────────────────────────────────────

from routers.auth      import router as auth_router
from routers.notebooks import router as notebooks_router
from routers.fuse      import router as fuse_router
from routers.learning  import router as learning_router
from routers.graph     import router as graph_router

app.include_router(auth_router)
app.include_router(notebooks_router)
app.include_router(fuse_router)
app.include_router(learning_router)
app.include_router(graph_router)


# ── Health + usage (trivial; fine here) ───────────────────────────────────────

@app.get("/health")
async def health():
    import deps
    return {
        "status":           "ok",
        "service":          "AuraGraph v0.6",
        "azure_configured": deps._is_azure_available(),
        "groq_configured":  deps._is_groq_available(),
        "llm_concurrency":  int(os.environ.get("LLM_CONCURRENCY", "1")),
        "rate_limits":      {"hourly": deps._LLM_HOURLY_LIMIT, "daily": deps._LLM_DAILY_LIMIT},
    }


@app.get("/api/usage")
async def get_usage(authorization: Optional[str] = Header(None)):
    """Return the calling user's LLM usage history (last 7 days)."""
    import sqlite3
    from datetime import datetime, timezone, timedelta
    from agents.auth_utils import DB_PATH
    import deps

    user      = deps.get_current_user(authorization)
    now       = datetime.now(timezone.utc)
    seven_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    con = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT day_bucket, SUM(calls) as calls, SUM(est_tokens) as tokens,
               SUM(est_cost_usd) as cost
        FROM llm_usage
        WHERE user_id=? AND day_bucket >= ?
        GROUP BY day_bucket ORDER BY day_bucket DESC
        """,
        (user["id"], seven_ago)
    ).fetchall()
    con.close()

    today_str   = now.strftime("%Y-%m-%d")
    hour_str    = now.strftime("%Y-%m-%dT%H")
    daily_calls = sum(r["calls"] for r in rows if r["day_bucket"] == today_str)
    hour_calls  = 0
    try:
        con2 = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        con2.row_factory = sqlite3.Row
        hr = con2.execute(
            "SELECT calls FROM llm_usage WHERE user_id=? AND hour_bucket=?",
            (user["id"], hour_str)
        ).fetchone()
        con2.close()
        if hr:
            hour_calls = hr["calls"]
    except Exception:
        pass

    return {
        "user_id":         user["id"],
        "limits":          {"hourly": deps._LLM_HOURLY_LIMIT, "daily": deps._LLM_DAILY_LIMIT},
        "this_hour_calls": hour_calls,
        "today_calls":     daily_calls,
        "history":         [dict(r) for r in rows],
    }
