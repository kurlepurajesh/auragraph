"""
Azure AI Content Safety — AuraGraph
────────────────────────────────────
Thin async wrapper around the Azure AI Content Safety REST API.

Applied to all LLM-generated text (mutations, doubt answers, practice questions)
before they are returned to the student.

Behaviour:
  • When AZURE_CONTENT_SAFETY_ENDPOINT + AZURE_CONTENT_SAFETY_KEY are both set
    in the environment, performs an actual API call.
  • When not configured, returns (True, "") instantly — zero latency / no error.
  • Always fails open: a network error or bad status still returns (True, "")
    so the student is never blocked due to a safety service outage.

Severity scale (Azure):
  0 – Safe   2 – Low   4 – Medium   6 – High
We flag severity ≥ 4 (medium+) as unsafe.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_ENDPOINT = os.environ.get("AZURE_CONTENT_SAFETY_ENDPOINT", "").rstrip("/")
_KEY      = os.environ.get("AZURE_CONTENT_SAFETY_KEY", "")
_API_VER  = "2024-09-01"
_CATEGORIES = ["Hate", "SelfHarm", "Sexual", "Violence"]
_THRESHOLD  = 4   # medium severity


def is_configured() -> bool:
    return bool(_ENDPOINT and _KEY)


async def check_content_safety(text: str) -> tuple[bool, str]:
    """
    Returns (is_safe, flagged_category).
    is_safe = True  → content is safe to return.
    is_safe = False → content was flagged; flagged_category names the severity.
    Always returns (True, "") when not configured.
    """
    if not is_configured():
        return True, ""

    import httpx

    url = f"{_ENDPOINT}/contentsafety/text:analyze?api-version={_API_VER}"
    payload = {
        "text": text[:5000],   # API max is 10 k chars; keep cost low
        "categories": _CATEGORIES,
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                url,
                headers={
                    "Ocp-Apim-Subscription-Key": _KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code != 200:
            logger.warning("Content Safety API returned %d", resp.status_code)
            return True, ""

        data = resp.json()
        for cat in data.get("categoriesAnalysis", []):
            severity = cat.get("severity", 0)
            if severity >= _THRESHOLD:
                category = cat.get("category", "unknown")
                logger.warning(
                    "Content Safety flagged '%s' at severity %d", category, severity
                )
                return False, category

        return True, ""

    except Exception as exc:
        logger.warning("Content Safety check failed (pass-through): %s", exc)
        return True, ""   # fail open
