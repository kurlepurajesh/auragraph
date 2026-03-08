"""
agents/content_safety.py — Azure AI Content Safety
────────────────────────────────────────────────────
Screens all LLM-generated text before returning it to the student.

Priority:
  1. Azure AI Content Safety SDK  (AZURE_CONTENT_SAFETY_ENDPOINT + KEY)
  2. Httpx fallback               (same endpoint, no SDK dependency)
  3. Pass-through (safe=True)     (never blocks on service outage)

Severity scale: 0=Safe  2=Low  4=Medium  6=High
We flag severity ≥ 4 as unsafe.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_ENDPOINT  = os.environ.get("AZURE_CONTENT_SAFETY_ENDPOINT", "").rstrip("/")
_KEY       = os.environ.get("AZURE_CONTENT_SAFETY_KEY", "")
_THRESHOLD = 4   # medium and above


def _is_configured() -> bool:
    return bool(_ENDPOINT and _KEY
                and "placeholder" not in _ENDPOINT.lower()
                and "your-" not in _KEY.lower())


async def check_content_safety(text: str) -> tuple[bool, str]:
    """
    Returns (is_safe, flagged_category).
    Always returns (True, "") when unconfigured or on any error (fail-open).
    """
    if not _is_configured():
        return True, ""

    # Try official Azure AI Content Safety SDK first
    try:
        from azure.ai.contentsafety import ContentSafetyClient
        from azure.ai.contentsafety.models import AnalyzeTextOptions, TextCategory
        from azure.core.credentials import AzureKeyCredential

        def _sync_call() -> tuple[bool, str]:
            client = ContentSafetyClient(
                endpoint=_ENDPOINT,
                credential=AzureKeyCredential(_KEY),
            )
            req = AnalyzeTextOptions(
                text=text[:10_000],
                categories=[
                    TextCategory.HATE,
                    TextCategory.SELF_HARM,
                    TextCategory.SEXUAL,
                    TextCategory.VIOLENCE,
                ],
            )
            try:
                resp = client.analyze_text(req)
            except Exception as e:
                logger.warning("Content Safety SDK error: %s", e)
                return True, ""

            for item in resp.categories_analysis:
                sev = item.severity or 0
                if sev >= _THRESHOLD:
                    logger.warning("Content Safety: '%s' severity=%d", item.category, sev)
                    return False, str(item.category)
            return True, ""

        return await asyncio.to_thread(_sync_call)

    except ImportError:
        pass   # SDK not installed — fall through to httpx

    except Exception as exc:
        logger.warning("Content Safety SDK call failed (pass-through): %s", exc)
        return True, ""

    # Httpx fallback
    try:
        import httpx
        url = f"{_ENDPOINT}/contentsafety/text:analyze?api-version=2024-09-01"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                url,
                headers={"Ocp-Apim-Subscription-Key": _KEY, "Content-Type": "application/json"},
                json={
                    "text": text[:5000],
                    "categories": ["Hate", "SelfHarm", "Sexual", "Violence"],
                },
            )
        if resp.status_code != 200:
            logger.warning("Content Safety httpx: HTTP %d", resp.status_code)
            return True, ""
        for cat in resp.json().get("categoriesAnalysis", []):
            if (cat.get("severity") or 0) >= _THRESHOLD:
                logger.warning("Content Safety: '%s' severity=%d flagged", cat.get("category"), cat.get("severity"))
                return False, cat.get("category", "unknown")
        return True, ""
    except Exception as exc:
        logger.warning("Content Safety httpx fallback failed (pass-through): %s", exc)
        return True, ""
