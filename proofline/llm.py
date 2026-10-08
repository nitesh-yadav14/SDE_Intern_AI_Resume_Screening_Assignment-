"""Optional LLM "second reviewer" — bounded, quote-verified, swappable.

The LLM never decides eligibility and never produces the score. It reviews the
AI projects the rules already found and may nudge ``ai_project_depth`` by at
most ±``max_adjustment`` points. Its output is:

1. **Schema-validated** — Pydantic ``LLMVerdict``; malformed JSON gets one
   repair retry, then the review is marked failed.
2. **Quote-verified** — every ``evidence_quote`` must actually occur in the
   resume (fuzzy token match). An adjustment whose supporting quotes are all
   fabricated is discarded. This is the hallucination guard.
3. **Cached** — keyed by (model, prompt version, resume hash).

Providers sit behind the ``Reviewer`` protocol. ``OpenAICompatibleReviewer``
works with OpenAI, Groq, Together, OpenRouter, Gemini's OpenAI endpoint or a
local Ollama — just change ``LLM_BASE_URL`` / ``LLM_MODEL``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Protocol

import requests
from pydantic import ValidationError

from .models import LLMReview, LLMVerdict

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior engineer reviewing a resume for an AI/agentic SDE internship.
A rule-based system has already scored the candidate. Your job is ONLY to judge the depth of the
AI projects it found, and to correct the rule-based AI score when it is clearly wrong.

Depth labels:
- thin_wrapper: sends a prompt to an LLM API and shows the answer; no retrieval, tools, state,
  evaluation, data processing or real product logic.
- moderate: one real mechanism (e.g. RAG over own data, structured extraction, a tool call).
- deep: several mechanisms working together (retrieval + agents/tools + state/evaluation),
  with ownership and measurable outcomes.

Rules:
- Every evidence_quote MUST be copied verbatim from the resume text (5-25 words). Quotes are checked.
- ai_depth_adjustment is an integer in [-15, 15]; 0 if the rule-based score is reasonable.
- Be skeptical of buzzwords without implementation detail.
- Respond with JSON only, matching this schema:
{schema}"""

USER_PROMPT = """RULE-BASED AI DEPTH SCORE: {ai_score}/40
AI PROJECT BLOCKS FOUND BY RULES: {blocks}

RESUME TEXT:
\"\"\"
{resume}
\"\"\""""


class Reviewer(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class OpenAICompatibleReviewer:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 45):
        self.api_key, self.base_url, self.model, self.timeout = api_key, base_url, model, timeout
        self.name = f"openai-compatible:{model}"

    def complete(self, system: str, user: str) -> str:
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# ── quote verification ───────────────────────────────────────────────────────

def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def quote_in_text(quote: str, text: str, threshold: float = 0.8) -> bool:
    """True if ≥80 % of the quote's tokens appear as a contiguous-ish window in the text."""
    q = _tokens(quote)
    if len(q) < 3:
        return False
    t = _tokens(text)
    joined = " ".join(t)
    if " ".join(q) in joined:
        return True
    qset = q
    win = len(q)
    best = 0.0
    for i in range(0, max(1, len(t) - win + 1)):
        window = set(t[i:i + win + 3])
        best = max(best, sum(1 for tok in qset if tok in window) / len(qset))
        if best >= threshold:
            return True
    return False


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if start != -1 and end != -1 else raw


# ── public entry point ───────────────────────────────────────────────────────

def review(reviewer: Reviewer | None, resume_text: str, resume_hash: str, ai_score: float, blocks: list[str],
           cfg: dict) -> LLMReview:
    if reviewer is None:
        return LLMReview(status="disabled", detail="rule-based only (no LLM configured)")
    cache_dir = Path(cfg["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{reviewer.name}|{cfg['prompt_version']}|{resume_hash}".encode()).hexdigest()[:24]
    cache_file = cache_dir / f"{key}.json"

    system = SYSTEM_PROMPT.format(schema=json.dumps(LLMVerdict.model_json_schema()))
    user = USER_PROMPT.format(ai_score=ai_score, blocks=json.dumps(blocks),
                              resume=resume_text[: cfg["max_resume_chars"]])
    verdict, status = None, "ok"
    if cache_file.is_file():
        try:
            verdict, status = LLMVerdict.model_validate_json(cache_file.read_text(encoding="utf-8")), "cached"
        except ValidationError:
            verdict = None
    if verdict is None:
        last_err = ""
        for attempt in range(2):                     # one repair retry on malformed output
            try:
                raw = reviewer.complete(system, user if attempt == 0 else
                                        user + f"\n\nYour previous reply was invalid ({last_err}). Return ONLY valid JSON.")
                verdict = LLMVerdict.model_validate_json(_extract_json(raw))
                cache_file.write_text(verdict.model_dump_json(indent=2), encoding="utf-8")
                break
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_err = type(exc).__name__
            except Exception as exc:                  # network / auth / provider errors
                return LLMReview(status="failed", provider=reviewer.name, detail=f"{type(exc).__name__}: {str(exc)[:120]}")
        if verdict is None:
            return LLMReview(status="failed", provider=reviewer.name, detail=f"invalid structured output ({last_err})")

    # hallucination guard
    good = [p for p in verdict.projects if quote_in_text(p.evidence_quote, resume_text)]
    rejected = len(verdict.projects) - len(good)
    verdict.projects = good
    adj = max(-cfg["max_adjustment"], min(cfg["max_adjustment"], verdict.ai_depth_adjustment))
    if adj and not good:
        adj, note = 0, "adjustment dropped: no verifiable quote supported it"
    else:
        note = verdict.adjustment_reason
    return LLMReview(status=status, provider=reviewer.name, detail=note, applied_adjustment=adj,
                     verified_quotes=len(good), rejected_quotes=rejected, verdict=verdict)


def build_reviewer(settings, enabled: bool) -> Reviewer | None:
    if not enabled:
        return None
    if not settings.llm_api_key:
        log.warning("--llm requested but LLM_API_KEY is not set; continuing rule-based only")
        return None
    return OpenAICompatibleReviewer(settings.llm_api_key, settings.llm_base_url, settings.llm_model,
                                    settings.section("llm")["timeout_seconds"])
