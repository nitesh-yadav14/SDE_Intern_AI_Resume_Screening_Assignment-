"""End-to-end orchestration: folder in → ranked, evidence-backed results out."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import eligibility, github, lexicon as lx, llm, scoring
from .config import Settings
from .ingest import discover, safe_read
from .models import CandidateResult, Evidence, LLMReview, ParsedResume

log = logging.getLogger(__name__)
CATEGORIES = ["ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"]


def matched_skills(resume: ParsedResume) -> list[str]:
    return [name for name, rx in lx.SKILL_NAMES.items() if rx.search(resume.text)]


def _confidence(resume: ParsedResume, card: scoring.ScoreCard) -> str:
    """How much of the score rests on applied evidence (projects/jobs) vs. skill-list claims,
    and how cleanly the PDF parsed. Tells a reviewer which ledgers to double-check."""
    positive = [e for e in card.ledger if e.points > 0 and e.category != "github"]
    applied = sum(e.points for e in positive if not e.note.startswith("×") and "skills only" not in e.signal)
    share = applied / max(1e-9, sum(e.points for e in positive))
    q = resume.extraction_quality
    if share >= 0.85 and q >= 0.72 and len(resume.sections_found) >= 4:
        return "high"
    if share >= 0.7 and q >= 0.6:
        return "medium"
    return "low"


def _score_one(resume: ParsedResume, settings: Settings) -> tuple[scoring.ScoreCard, set[str]]:
    ctx_w = settings.section("context_weight")
    card = scoring.ScoreCard()
    present = scoring.score_rubric(card, resume, ctx_w, settings.weights)
    scoring.score_ai(card, resume, settings.section("ai_depth"), ctx_w, settings.weights["ai_project_depth"])
    return card, present


def run(input_dir: Path, settings: Settings, use_github: bool = True, use_llm: bool = False,
        workers: int = 4) -> dict:
    t0 = time.perf_counter()
    files = discover(input_dir)
    results: list[CandidateResult] = []
    parsed: dict[str, ParsedResume] = {}
    seen_hash: dict[str, str] = {}
    seen_email: dict[str, str] = {}

    # 1 ── ingest in a bounded process pool (PDF parsing is CPU-bound) ──────
    #      one bad file never stops the batch; results keep folder order
    if workers > 1 and len(files) > 4:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            reads = list(pool.map(safe_read, files, chunksize=2))
    else:
        reads = [safe_read(p) for p in files]
    t_parse = time.perf_counter() - t0
    for fname, r, err in reads:
        if r is None:
            results.append(CandidateResult(file=fname, candidate_name=None, email=None, status="failed",
                                           eligible=False, error=err))
            continue
        dup = seen_hash.get(r.sha256) or (seen_email.get(r.email) if r.email else None)
        if dup:
            results.append(CandidateResult(file=fname, candidate_name=r.name, email=r.email, status="duplicate",
                                           eligible=False, duplicate_of=dup,
                                           rejection_reasons=[f"Duplicate of {dup} (same file or same email)"]))
            continue
        seen_hash[r.sha256] = fname
        if r.email:
            seen_email[r.email] = fname
        parsed[fname] = r

    # 2 ── hard eligibility gate ───────────────────────────────────────────────
    elig = {name: eligibility.check(r, settings.section("eligibility")) for name, r in parsed.items()}

    # 3 ── rule-based evidence scoring for eligible candidates ────────────────
    cards = {n: _score_one(parsed[n], settings) for n, e in elig.items() if e.eligible}

    # 4 ── GitHub enrichment (bounded concurrency, cached, failure-tolerant) ──
    gh_cfg = settings.section("github")
    client = github.GitHubClient(settings.github_token, gh_cfg["cache_dir"], gh_cfg["timeout_seconds"],
                                 offline=not use_github)
    eligible_names = list(cards)
    profiles = dict(zip(eligible_names, client.fetch_many([parsed[n].github_username for n in eligible_names],
                                                          gh_cfg["max_workers"])))

    # 5 ── optional LLM second review (bounded, quote-verified) ───────────────
    llm_cfg = settings.section("llm")
    reviewer = llm.build_reviewer(settings, use_llm)

    def _review(name: str) -> LLMReview:
        card, _ = cards[name]
        blocks = [b.block.title for b in card.ai_blocks[:4]]
        try:
            return llm.review(reviewer, parsed[name].text, parsed[name].sha256, card.total("ai_project_depth"),
                              blocks, llm_cfg)
        except Exception as exc:  # pragma: no cover
            return LLMReview(status="failed", detail=str(exc)[:160])

    with ThreadPoolExecutor(max_workers=llm_cfg["max_workers"]) as pool:
        reviews = dict(zip(eligible_names, pool.map(_review, eligible_names)))

    # 6 ── assemble ────────────────────────────────────────────────────────────
    for name, r in parsed.items():
        e = elig[name]
        base = dict(file=name, candidate_name=r.name, email=r.email, matched_skills=matched_skills(r),
                    parse_meta={"extractor": r.extractor, "extraction_quality": r.extraction_quality,
                                "sections_found": r.sections_found, "github_username": r.github_username})
        if not e.eligible:
            results.append(CandidateResult(**base, status="rejected", eligible=False,
                                           rejection_reasons=e.rejection_reasons,
                                           evidence_ledger=e.python_evidence + e.ai_evidence))
            continue
        card, present = cards[name]
        gh_ev, gh_summary = github.score(profiles[name], gh_cfg)
        card.ledger.extend(gh_ev)
        card.cap("github", settings.weights["github"])
        rv = reviews[name]
        if rv.applied_adjustment:
            card.add(category="ai_project_depth", signal="LLM reviewer adjustment", points=rv.applied_adjustment,
                     context="llm review", note=rv.detail[:200],
                     quote=rv.verdict.projects[0].evidence_quote if rv.verdict and rv.verdict.projects else "")
            card.cap("ai_project_depth", settings.weights["ai_project_depth"])
        breakdown = {c: card.total(c) for c in CATEGORIES}
        total = round(sum(breakdown.values()), 1)
        summary, strengths, concerns = scoring.narrate(card, present, settings.weights)
        if profiles[name].status == "no_profile":
            concerns.append("No GitHub profile linked")
        if rv.verdict:
            strengths += [s for s in rv.verdict.strengths[:2] if s not in strengths]
            concerns += [c for c in rv.verdict.concerns[:2] if c not in concerns]
        results.append(CandidateResult(
            **base, status="eligible", eligible=True, total_score=total, tier=scoring.tier(total),
            confidence=_confidence(r, card), score_breakdown=breakdown, project_summary=summary,
            github=profiles[name], github_summary=gh_summary, strengths=strengths, concerns=concerns,
            evidence_ledger=sorted(card.ledger, key=lambda ev: (CATEGORIES.index(ev.category), -ev.points)),
            llm_review=rv,
        ))

    # 7 ── rank: score, then AI depth, then backend as deterministic tie-breaks
    ranked = sorted((c for c in results if c.eligible),
                    key=lambda c: (-c.total_score, -c.score_breakdown["ai_project_depth"],
                                   -c.score_breakdown["python_backend"], c.file))
    for i, c in enumerate(ranked, 1):
        c.rank = i
    rejected = sorted((c for c in results if c.status in ("rejected", "duplicate")), key=lambda c: c.file)
    failed = sorted((c for c in results if c.status == "failed"), key=lambda c: c.file)

    gh_status: dict[str, int] = {}
    for p in profiles.values():
        gh_status[p.status] = gh_status.get(p.status, 0) + 1
    reason_counts: dict[str, int] = {}
    for c in rejected:
        for reason in c.rejection_reasons:
            key = ("Duplicate" if reason.startswith("Duplicate")
                   else "No Python evidence" if "Python" in reason
                   else "Classical ML only (no LLM/agentic work)" if "classical" in reason
                   else "AI only in skills list" if "only in skills" in reason
                   else "No AI/agentic evidence")
            reason_counts[key] = reason_counts.get(key, 0) + 1
    return {
        "meta": {
            "tool": "proofline", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input_dir": str(input_dir), "weights": settings.weights,
            "llm": reviewer.name if reviewer else "disabled (rule-based only)",
            "github": "enabled" if use_github else "disabled",
            "runtime_seconds": round(time.perf_counter() - t0, 2),
            "parse_seconds": round(t_parse, 2), "parse_workers": workers,
        },
        "batch_summary": {
            "total_resumes": len(files),
            "successfully_parsed": len(parsed),
            "eligible": len(ranked),
            "rejected": sum(1 for c in rejected if c.status == "rejected"),
            "duplicates": sum(1 for c in rejected if c.status == "duplicate"),
            "failed_unreadable": len(failed),
            "rejection_reasons": reason_counts,
            "github_enrichment": gh_status,
            "tiers": {t: sum(1 for c in ranked if c.tier == t) for t in
                      ("Strong shortlist", "Shortlist", "Consider", "Low fit")},
        },
        "ranking": [c.model_dump(exclude_none=True) for c in ranked],
        "rejected": [c.model_dump(exclude_none=True, exclude={"score_breakdown"}) for c in rejected],
        "failed": [c.model_dump(exclude_none=True) for c in failed],
    }
