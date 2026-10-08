"""Tests for the decisions that matter most: who gets rejected, and why scores move."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from proofline import eligibility, github, llm, scoring
from proofline.config import load_settings
from proofline.ingest import ResumeReadError, _despace, find_github, find_name, read_resume
from proofline.pipeline import _score_one, run

SETTINGS = load_settings()
ELIG = SETTINGS.section("eligibility")


def resume(tmp_path: Path, body: str, name: str = "r.txt"):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return read_resume(p)


HEADER = "Asha Rao\nasha@example.com | github.com/asharao\n"
DEEP_AI = HEADER + """
Skills
Python, FastAPI, PostgreSQL, Redis, Docker, GCP, LangGraph
Experience
AI Engineer Intern | Acme Labs | Jan 2025 - Present
Built a LangGraph multi-agent support assistant with tool calling and conversation memory, served via FastAPI.
Implemented a RAG pipeline: ingestion, chunking, embeddings in pgvector, hybrid search and re-ranking.
Added an evaluation harness (RAGAS faithfulness) and guardrails; deployed on Cloud Run with Docker, 2,000+ users.
Projects
DocQA | Python, FastAPI, Redis, pytest
Async FastAPI service with Redis caching and retries; LLM answers grounded by vector search over 10,000 documents.
"""
WRAPPER_AI = HEADER + """
Skills
Python, Flask
Projects
Gemini Chatbot | Python, Streamlit
Built a chatbot that sends the user prompt to the Gemini API and displays the response in a Streamlit page for users.
"""
JS_ONLY = HEADER + """
Skills
JavaScript, TypeScript, React, Next.js, Node.js, LangChain.js
Projects
AI Notes | Next.js, OpenAI API
Built a RAG notes app with OpenAI embeddings and a Pinecone vector store, written fully in TypeScript and Node.js.
"""
PYTHON_NO_AI = HEADER + """
Skills
Python, Django, PostgreSQL
Projects
Library System | Django, PostgreSQL
Built a library management system with REST APIs, role-based auth and PostgreSQL full-text search for 500 users.
"""
SKILLS_ONLY_AI = HEADER + """
Skills
Python, LangChain, LangGraph, RAG, LLMs
Projects
Expense Tracker | Python, Flask
Built an expense tracker with Flask and SQLite with charts, CSV export and monthly budget alerts for students.
"""
COPILOT_ONLY = HEADER + """
Skills
Python, Django
Experience
Backend Intern | Foo Corp | Jan 2024 - Jun 2024
Built Django REST APIs for invoicing; used GitHub Copilot and AI tools (Cursor, ChatGPT) to speed up development.
"""


# ── eligibility ──────────────────────────────────────────────────────────────

def test_deep_python_ai_candidate_is_eligible(tmp_path):
    r = eligibility.check(resume(tmp_path, DEEP_AI), ELIG)
    assert r.eligible and not r.rejection_reasons
    assert r.ai_evidence and r.python_evidence


def test_javascript_only_profile_is_rejected_even_with_ai(tmp_path):
    r = eligibility.check(resume(tmp_path, JS_ONLY), ELIG)
    assert not r.eligible
    assert any("Python" in reason for reason in r.rejection_reasons)


def test_python_without_ai_is_rejected(tmp_path):
    r = eligibility.check(resume(tmp_path, PYTHON_NO_AI), ELIG)
    assert not r.eligible
    assert any("AI" in reason for reason in r.rejection_reasons)


def test_ai_keywords_only_in_skills_list_are_not_evidence(tmp_path):
    r = eligibility.check(resume(tmp_path, SKILLS_ONLY_AI), ELIG)
    assert not r.eligible
    assert "only in skills" in r.rejection_reasons[0]


def test_using_ai_coding_assistants_is_not_ai_engineering(tmp_path):
    r = eligibility.check(resume(tmp_path, COPILOT_ONLY), ELIG)
    assert not r.eligible


def test_react_alongside_python_and_ai_is_fine(tmp_path):
    body = DEEP_AI + "\nPortfolio | React, Next.js\nBuilt a React dashboard over the FastAPI agent backend.\n"
    assert eligibility.check(resume(tmp_path, body), ELIG).eligible


# ── scoring ──────────────────────────────────────────────────────────────────

def _card(tmp_path, body):
    return _score_one(resume(tmp_path, body), SETTINGS)


def test_ledger_sums_to_category_scores_and_respects_caps(tmp_path):
    card, _ = _card(tmp_path, DEEP_AI)
    for cat, cap in SETTINGS.weights.items():
        total = card.total(cat)
        assert 0 <= total <= cap, cat
    assert card.total("ai_project_depth") >= 30          # deep, multi-capability AI work


def test_thin_wrapper_is_penalised_and_ranks_far_below_deep_project(tmp_path):
    deep, _ = _card(tmp_path, DEEP_AI)
    thin, _ = _card(tmp_path, WRAPPER_AI)
    assert any(e.signal == "thin LLM-wrapper project" and e.points < 0 for e in thin.ledger)
    assert thin.total("ai_project_depth") < deep.total("ai_project_depth") - 20


def test_skill_used_in_project_beats_skill_in_list(tmp_path):
    in_project = HEADER + "Projects\nAgent API | Python\nBuilt an LLM agent service with FastAPI and RAG retrieval for 300 users.\n"
    in_list = HEADER + "Skills\nPython, FastAPI\nProjects\nAgent Bot | Python\nBuilt an LLM agent with RAG retrieval that answers course questions well.\n"
    a, _ = _card(tmp_path, in_project)
    b, _ = _card(tmp_path, in_list)
    fa = next(e for e in a.ledger if e.signal == "FastAPI")
    fb = next(e for e in b.ledger if e.signal == "FastAPI")
    assert fa.points > fb.points
    assert fb.note.startswith("×")                       # discounted, and says why


def test_every_positive_rubric_point_carries_a_quote(tmp_path):
    card, _ = _card(tmp_path, DEEP_AI)
    for e in card.ledger:
        if e.points > 0 and e.category != "github":
            assert e.quote, e.signal


# ── GitHub ───────────────────────────────────────────────────────────────────

def _repo(name, days, lang="Python", fork=False, desc=""):
    pushed = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    return {"name": name, "pushed_at": pushed, "language": lang, "fork": fork, "description": desc, "topics": []}


def test_github_scoring_rewards_recent_relevant_original_repos():
    prof = github.summarise("u", {"public_repos": 4}, [
        _repo("rag-bot", 5), _repo("agent-lab", 40, lang="TypeScript", desc="LLM agent playground"),
        _repo("forked-langchain", 1, fork=True), _repo("old-site", 900, lang="HTML")])
    ev, summary = github.score(prof, SETTINGS.section("github"))
    pts = sum(e.points for e in ev)
    assert prof.days_since_last_push == 5 and "forked-langchain" not in prof.relevant_repos
    assert pts == 5 + 3.0 and "/10" in summary


def test_github_failure_is_recorded_not_raised(tmp_path, monkeypatch):
    client = github.GitHubClient(None, tmp_path)

    def boom(path):
        raise github.requests.ConnectionError("offline")
    monkeypatch.setattr(client, "_get", boom)
    prof = client.fetch("someone")
    assert prof.status == "unreachable"
    assert client.fetch("another").status == "skipped"    # circuit breaker: no more calls this run
    assert github.score(prof, SETTINGS.section("github"))[0] == []


# ── LLM adapter ──────────────────────────────────────────────────────────────

class FakeReviewer:
    name = "fake"

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, system, user):
        self.calls += 1
        return self.reply if isinstance(self.reply, str) else self.reply[self.calls - 1]


def _llm_cfg(tmp_path):
    return {**SETTINGS.section("llm"), "cache_dir": str(tmp_path / "llm")}


def test_llm_adjustment_is_clamped_and_needs_verified_quotes(tmp_path):
    text = "Built a LangGraph agent with tool calling and memory for support tickets"
    real = ('{"projects":[{"title":"x","depth":"deep","evidence_quote":"LangGraph agent with tool calling and memory"}],'
            '"ai_depth_adjustment":14}')
    rv = llm.review(FakeReviewer(real), text, "h1", 20, [], _llm_cfg(tmp_path))
    assert rv.applied_adjustment == SETTINGS.section("llm")["max_adjustment"]

    fake = ('{"projects":[{"title":"x","depth":"deep","evidence_quote":"led a team of 40 researchers at DeepMind"}],'
            '"ai_depth_adjustment":6}')
    rv = llm.review(FakeReviewer(fake), text, "h2", 20, [], _llm_cfg(tmp_path))
    assert rv.applied_adjustment == 0 and rv.rejected_quotes == 1     # hallucinated quote → no effect


def test_llm_malformed_output_gets_one_retry_then_fails_gracefully(tmp_path):
    good = '{"projects":[],"ai_depth_adjustment":0}'
    rv = llm.review(FakeReviewer(["not json", good]), "text here ok", "h3", 10, [], _llm_cfg(tmp_path))
    assert rv.status == "ok"
    rv = llm.review(FakeReviewer(["nope", "still nope"]), "text here ok", "h4", 10, [], _llm_cfg(tmp_path))
    assert rv.status == "failed"


# ── ingestion & batch robustness ─────────────────────────────────────────────

def test_letter_spaced_text_is_repaired():
    assert _despace("S K I L L S  P y t h o n  F a s t A P I") == "SKILLS Python FastAPI"


def test_github_username_from_hidden_link_annotation():
    assert find_github("GitHub", ["https://github.com/Jane-Doe/agent-repo", "https://github.com/jane-doe"]) == "Jane-Doe"


def test_name_ignores_glued_location():
    assert find_name(["Atul KumarDehradun, Uttarakhand, India"]) == "Atul Kumar"


def test_corrupt_file_does_not_crash_the_batch(tmp_path):
    (tmp_path / "good.txt").write_text(DEEP_AI, encoding="utf-8")
    (tmp_path / "copy.txt").write_text(DEEP_AI, encoding="utf-8")      # duplicate
    (tmp_path / "broken.pdf").write_bytes(b"this is not a pdf")
    (tmp_path / "empty.pdf").write_bytes(b"")
    (tmp_path / "js.txt").write_text(JS_ONLY.replace("asha@", "other@"), encoding="utf-8")
    out = run(tmp_path, SETTINGS, use_github=False)
    s = out["batch_summary"]
    assert s["total_resumes"] == 5 and s["failed_unreadable"] == 2 and s["duplicates"] == 1
    assert s["eligible"] == 1 and out["ranking"][0]["rank"] == 1
    top = out["ranking"][0]
    assert abs(sum(e["points"] for e in top["evidence_ledger"]) - top["total_score"]) < 0.2


def test_unreadable_pdf_raises_typed_error(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4 garbage")
    with pytest.raises(ResumeReadError):
        read_resume(p)
