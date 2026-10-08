"""Lightweight public-GitHub enrichment (max 10 points, never blocks screening).

Two API calls per user (profile + repos sorted by push date), cached on disk
so re-runs are free and rate limits are rarely hit. Calls run through a
bounded thread pool. Every failure mode becomes a *status* on the candidate
rather than an exception.

Scoring (explainable, 0–10)
  activity  (0–5): recency of the latest push to an original public repo
                   ≤30d → 5, ≤90d → 4, ≤180d → 3, ≤365d → 2, older → 1
                   +0 bonus/penalty for volume — recency is what we're asking
  relevance (0–5): original (non-fork) repos that are Python or AI-flavoured
                   AND pushed in the last 12 months: 1.5 pts each, max 5
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

from .models import Evidence, GitHubProfile

log = logging.getLogger(__name__)
API = "https://api.github.com"
AI_REPO = re.compile(r"\b(ai|llm|rag|agent|agents|agentic|gpt|langchain|langgraph|chatbot|embedding|vector|ml|nlp|"
                     r"genai|copilot|assistant|semantic)\b", re.I)


class GitHubClient:
    def __init__(self, token: str | None, cache_dir: str | Path, timeout: float = 8, offline: bool = False):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "proofline-screener"})
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.offline = offline
        self._memo: dict[str, GitHubProfile] = {}
        self._circuit_open = False      # stop hammering the API after a rate-limit / network failure

    # one cached GET
    def _get(self, path: str):
        resp = self.session.get(API + path, timeout=self.timeout)
        if resp.status_code == 404:
            raise LookupError("not found")
        if resp.status_code in (403, 429) and ("rate limit" in resp.text.lower() or resp.headers.get("X-RateLimit-Remaining") == "0"):
            raise PermissionError("rate limited")
        resp.raise_for_status()
        return resp.json()

    def fetch(self, username: str | None) -> GitHubProfile:
        if not username:
            return GitHubProfile(status="no_profile", detail="no GitHub URL found in resume")
        key = username.lower()
        if key in self._memo:
            return self._memo[key]
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.is_file():
            try:
                prof = GitHubProfile.model_validate_json(cache_file.read_text(encoding="utf-8"))
                prof.from_cache = True
                self._memo[key] = prof
                return prof
            except Exception:
                pass
        if self.offline:
            return GitHubProfile(username=username, status="skipped", detail="GitHub enrichment disabled (--no-github)")
        if self._circuit_open:
            return GitHubProfile(username=username, status="skipped",
                                 detail="skipped: GitHub API unavailable earlier in this run")
        try:
            user = self._get(f"/users/{username}")
            repos = self._get(f"/users/{username}/repos?per_page=100&sort=pushed&type=owner")
            prof = summarise(username, user, repos)
            cache_file.write_text(prof.model_dump_json(indent=2), encoding="utf-8")
        except LookupError:
            prof = GitHubProfile(username=username, status="not_found", detail="profile does not exist or is private")
        except PermissionError:
            self._circuit_open = True
            prof = GitHubProfile(username=username, status="rate_limited",
                                 detail="GitHub rate limit hit — set GITHUB_TOKEN for 5,000 req/h")
        except requests.RequestException as exc:
            self._circuit_open = True
            prof = GitHubProfile(username=username, status="unreachable", detail=f"network error: {type(exc).__name__}")
        except Exception as exc:  # never let enrichment kill the batch
            prof = GitHubProfile(username=username, status="error", detail=str(exc)[:160])
        self._memo[key] = prof
        return prof

    def fetch_many(self, usernames: list[str | None], max_workers: int = 4) -> list[GitHubProfile]:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(self.fetch, usernames))


def _days_since(iso: str | None, now: datetime) -> int | None:
    if not iso:
        return None
    return (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def summarise(username: str, user: dict, repos: list[dict], now: datetime | None = None) -> GitHubProfile:
    now = now or datetime.now(timezone.utc)
    own = [r for r in repos if not r.get("fork") and not r.get("archived")]
    pushes = [d for d in (_days_since(r.get("pushed_at"), now) for r in own) if d is not None]
    relevant = []
    for r in own:
        age = _days_since(r.get("pushed_at"), now)
        blob = " ".join(filter(None, [r.get("name", "").replace("-", " ").replace("_", " "),
                                      r.get("description") or "", " ".join(r.get("topics") or [])]))
        if age is not None and age <= 365 and ((r.get("language") or "").lower() in ("python", "jupyter notebook")
                                               or AI_REPO.search(blob)):
            relevant.append(r["name"])
    langs: dict[str, int] = {}
    for r in own:
        if r.get("language"):
            langs[r["language"]] = langs.get(r["language"], 0) + 1
    return GitHubProfile(
        username=username, status="ok", public_repos=user.get("public_repos"),
        days_since_last_push=min(pushes) if pushes else None,
        active_repos_90d=sum(1 for d in pushes if d <= 90), relevant_repos=relevant[:8],
        top_languages=[k for k, _ in sorted(langs.items(), key=lambda kv: -kv[1])[:4]],
    )


def score(profile: GitHubProfile, cfg: dict) -> tuple[list[Evidence], str]:
    """Return ledger lines and a one-line human summary."""
    if profile.status != "ok":
        label = {"no_profile": "No GitHub profile in resume", "not_found": "GitHub profile not found / private",
                 "rate_limited": "GitHub rate-limited — not scored", "unreachable": "GitHub API unreachable — not scored",
                 "skipped": "GitHub enrichment skipped", "error": "GitHub enrichment error"}[profile.status]
        return [], f"{label} (0/10, not held against eligibility)"
    ev: list[Evidence] = []
    d = profile.days_since_last_push
    act = 0 if d is None else 5 if d <= 30 else 4 if d <= 90 else 3 if d <= 180 else 2 if d <= 365 else 1
    act = min(act, cfg["activity_points"])
    if act:
        ev.append(Evidence(category="github", signal="recent public activity", points=act, context="github api",
                           quote=f"last push {d} days ago; {profile.active_repos_90d} repo(s) active in 90 days"))
    rel = min(cfg["relevance_points"], round(1.5 * len(profile.relevant_repos), 1))
    if rel:
        ev.append(Evidence(category="github", signal="maintained Python/AI repos", points=rel, context="github api",
                           quote=", ".join(profile.relevant_repos[:5])))
    when = "never pushed" if d is None else f"last push {d}d ago"
    summary = (f"@{profile.username}: {profile.public_repos} public repos, {when}, "
               f"{len(profile.relevant_repos)} recent Python/AI repo(s) → {act + rel:g}/10")
    return ev, summary
