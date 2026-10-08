"""Typed data contracts for the whole pipeline (Pydantic v2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Section = Literal["summary", "skills", "experience", "projects", "education", "certifications", "other"]
Category = Literal["ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"]


class Line(BaseModel):
    """One normalised resume line with the section it was found in."""
    no: int
    text: str
    section: Section
    block: int | None = None          # project/job block id (experience & projects only)


class Block(BaseModel):
    id: int
    section: Section
    title: str
    lines: list[int]                  # line numbers
    word_count: int


class ParsedResume(BaseModel):
    file: str
    sha256: str
    extractor: str
    extraction_quality: float = Field(ge=0, le=1)
    text: str
    lines: list[Line]
    blocks: list[Block]
    links: list[str] = []
    name: str | None = None
    email: str | None = None
    github_username: str | None = None
    sections_found: list[str] = []


class Evidence(BaseModel):
    """A single ledger line: points awarded (or deducted) and the proof."""
    category: Category
    signal: str
    points: float
    quote: str = ""
    line: int | None = None
    context: str = ""                 # section / block title / 'github api' / 'llm review'
    note: str = ""


class EligibilityResult(BaseModel):
    eligible: bool
    rejection_reasons: list[str] = []
    python_evidence: list[Evidence] = []
    ai_evidence: list[Evidence] = []


class GitHubProfile(BaseModel):
    username: str | None = None
    status: Literal["ok", "no_profile", "not_found", "rate_limited", "error", "skipped", "unreachable"] = "no_profile"
    detail: str = ""
    public_repos: int | None = None
    days_since_last_push: int | None = None
    active_repos_90d: int = 0
    relevant_repos: list[str] = []
    top_languages: list[str] = []
    from_cache: bool = False


class LLMVerdict(BaseModel):
    """Structured output the LLM must return (validated, then quote-checked)."""

    class ProjectAssessment(BaseModel):
        title: str
        depth: Literal["thin_wrapper", "moderate", "deep"]
        evidence_quote: str = Field(description="verbatim quote from the resume supporting the depth judgement")
        ownership_clear: bool = True

    projects: list[ProjectAssessment] = []
    ai_depth_adjustment: int = Field(0, ge=-15, le=15,
                                     description="suggested correction to the rule-based AI depth score")
    adjustment_reason: str = ""
    strengths: list[str] = []
    concerns: list[str] = []


class LLMReview(BaseModel):
    status: Literal["disabled", "ok", "failed", "cached"] = "disabled"
    provider: str = ""
    detail: str = ""
    applied_adjustment: float = 0
    verified_quotes: int = 0
    rejected_quotes: int = 0
    verdict: LLMVerdict | None = None


class CandidateResult(BaseModel):
    rank: int | None = None
    file: str
    candidate_name: str | None
    email: str | None
    status: Literal["eligible", "rejected", "failed", "duplicate"]
    eligible: bool
    total_score: float | None = None
    tier: str | None = None
    confidence: str | None = None
    score_breakdown: dict[str, float] | None = None
    rejection_reasons: list[str] = []
    matched_skills: list[str] = []
    project_summary: str = ""
    github: GitHubProfile | None = None
    github_summary: str = ""
    strengths: list[str] = []
    concerns: list[str] = []
    evidence_ledger: list[Evidence] = []
    llm_review: LLMReview | None = None
    duplicate_of: str | None = None
    error: str | None = None
    parse_meta: dict = {}
