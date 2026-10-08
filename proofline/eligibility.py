"""Hard eligibility gate — pure rules, no LLM, fully unit-testable.

Rule 1  Python evidence
    "Python" (or a Python-only framework such as Django/FastAPI) appears in
    skills, experience, projects or summary. A mention that exists *only* in
    certifications / coursework ("Crash Course on Python") is not enough.

Rule 2  AI / agentic evidence
    At least one AI anchor (LLM, RAG/retrieval, agent framework, embeddings…)
    inside an experience or project entry. AI words that live only in the
    skills list or summary are a claim, not evidence → rejected.

JavaScript / Java / React are never a reason to reject on their own.
"""
from __future__ import annotations

from . import lexicon as lx
from .evidence import find
from .models import EligibilityResult, Evidence, ParsedResume


def _strong_line(text: str) -> bool:
    """Line contains an unambiguous AI term (not just 'agent'/'transformer')."""
    stripped = lx.WEAK_ANCHOR_ONLY.sub(" ", lx.AI_TOOL_USAGE.sub(" ", text))
    return any(lx.AI_CAPABILITIES[c].search(stripped) for c in ("framework", "retrieval", "llm"))


def _ai_hits(resume: ParsedResume, sections: set[str]):
    block_text: dict[int, str] = {}
    for ln in resume.lines:
        if ln.block is not None:
            block_text[ln.block] = block_text.get(ln.block, "") + " " + ln.text
    hits = []
    for cap in sorted(lx.AI_ANCHORS):
        for h in find(lx.AI_CAPABILITIES[cap], resume.lines, sections, mask=lx.AI_TOOL_USAGE):
            if lx.WEAK_ANCHOR_ONLY.fullmatch(h.match.strip()):
                # 'agent' (travel agent) / 'transformer' (power grid) need a strong AI term nearby
                ctx = block_text.get(h.line.block, h.line.text) if h.line.block is not None else h.line.text
                if not _strong_line(ctx):
                    continue
            hits.append((cap, h))
    # strongest evidence first: frameworks/retrieval/agents before generic LLM mentions
    order = {"framework": 0, "retrieval": 1, "agents": 2, "llm": 3}
    hits.sort(key=lambda ch: (order[ch[0]], ch[1].line.no))
    return hits


def check(resume: ParsedResume, cfg: dict) -> EligibilityResult:
    py_ctx = set(cfg["python_contexts"])
    ai_ctx = set(cfg["ai_contexts"])
    reasons: list[str] = []

    # ── Python ────────────────────────────────────────────────────────────────
    py_hits = find(lx.PYTHON, resume.lines, py_ctx)
    implied = [] if py_hits else find(lx.PYTHON_FRAMEWORKS, resume.lines, py_ctx | {"experience", "projects"})
    py_evidence = [Evidence(category="python_backend", signal="python", points=0, quote=h.quote(), line=h.line.no,
                            context=h.line.section) for h in (py_hits or implied)[:3]]
    if implied and not py_hits:
        py_evidence[0].note = f"implied by Python framework '{implied[0].match}'"
    if not py_evidence:
        anywhere = find(lx.PYTHON, resume.lines)
        if anywhere:
            reasons.append(f"Python only appears in {anywhere[0].line.section} "
                           f"(\"{anywhere[0].quote(80)}\") — not as a working skill")
        else:
            reasons.append("No evidence of Python in skills, projects or experience")

    # ── AI / agentic ──────────────────────────────────────────────────────────
    applied = _ai_hits(resume, ai_ctx)
    ai_evidence = [Evidence(category="ai_project_depth", signal=cap, points=0, quote=h.quote(), line=h.line.no,
                            context=h.line.section) for cap, h in applied[:4]]
    if not applied:
        claimed = _ai_hits(resume, {"skills", "summary", "certifications", "education"})
        if claimed:
            names = sorted({h.match.strip() for _, h in claimed})[:5]
            reasons.append("AI/LLM terms (" + ", ".join(names) + ") appear only in skills/summary — "
                           "no project or work entry shows them being used")
        elif find(lx.CLASSIC_ML, resume.lines):
            reasons.append("Only classical ML/DL (e.g. CNN, scikit-learn) — no LLM/RAG/agentic project evidence")
        else:
            reasons.append("No AI/LLM/RAG/agentic project evidence")

    return EligibilityResult(eligible=not reasons, rejection_reasons=reasons,
                             python_evidence=py_evidence, ai_evidence=ai_evidence)
