"""Evidence-ledger scoring.

The score is never computed and *then* explained. The ledger is built first —
one line per awarded/deducted point, each with the resume quote that earned
it — and the category score is simply the sum of its ledger lines (category
caps appear as explicit negative lines). So ``sum(ledger) == total_score``
always holds, and tests assert it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import lexicon as lx
from .evidence import Hit, block_lines, find
from .models import Block, Evidence, ParsedResume

CAPABILITY_LABEL = {
    "retrieval": "retrieval / RAG", "agents": "agents & tool use", "framework": "orchestration framework",
    "state": "state / memory", "evaluation": "evaluation / guardrails", "data_pipeline": "data pipeline",
    "product_backend": "wired into a backend/product", "llm": "LLM integration", "shipped": "shipped / measured impact",
}


@dataclass
class AIBlock:
    block: Block
    caps: dict[str, Hit]
    raw_points: float = 0.0
    thin: bool = False
    tutorial: bool = False

    @property
    def substantive(self) -> set[str]:
        return set(self.caps) & lx.SUBSTANTIVE_AI


@dataclass
class ScoreCard:
    ledger: list[Evidence] = field(default_factory=list)
    ai_blocks: list[AIBlock] = field(default_factory=list)

    def add(self, **kw) -> None:
        kw["points"] = round(kw["points"], 2)
        if kw["points"]:
            self.ledger.append(Evidence(**kw))

    def total(self, category: str) -> float:
        return round(sum(e.points for e in self.ledger if e.category == category), 2)

    def cap(self, category: str, limit: float) -> None:
        cur = self.total(category)
        if cur > limit:
            self.add(category=category, signal="category cap", points=limit - cur, note=f"capped at {limit}")
        elif cur < 0:
            self.add(category=category, signal="floor", points=-cur, note="category cannot go below 0")


# ── AI / agentic depth ───────────────────────────────────────────────────────

def _strong(text: str) -> bool:
    stripped = lx.WEAK_ANCHOR_ONLY.sub(" ", lx.AI_TOOL_USAGE.sub(" ", text))
    return any(lx.AI_CAPABILITIES[c].search(stripped) for c in ("framework", "retrieval", "llm"))


def analyse_ai_blocks(resume: ParsedResume) -> list[AIBlock]:
    """Find project/job entries that contain AI work and profile what they do."""
    groups: list[tuple[Block, list]] = [(b, block_lines(resume, b)) for b in resume.blocks]
    other = [ln for ln in resume.lines if ln.section == "other"]
    if other:  # unsegmented resume: treat the unknown area as one pseudo-block
        groups.append((Block(id=-1, section="other", title="(unsectioned text)", lines=[l.no for l in other],
                             word_count=sum(len(l.text.split()) for l in other)), other))
    out = []
    for block, lines in groups:
        text = " ".join(l.text for l in lines)
        if not _strong(text):
            continue                                  # no unambiguous AI term → not an AI block
        caps: dict[str, Hit] = {}
        for cap, rx in lx.AI_CAPABILITIES.items():
            hits = find(rx, lines, mask=lx.AI_TOOL_USAGE)
            if hits:
                caps[cap] = hits[0]
        if not caps.keys() & lx.AI_ANCHORS:
            continue
        ab = AIBlock(block, caps)
        ab.thin = "llm" in caps and not ab.substantive
        ab.tutorial = block.word_count < 18 or bool(lx.TUTORIAL.search(text))
        out.append(ab)
    return out


def score_ai(card: ScoreCard, resume: ParsedResume, cfg: dict, ctx_w: dict, limit: float) -> None:
    pts = cfg["capability_points"]
    blocks = analyse_ai_blocks(resume)
    for ab in blocks:
        ab.raw_points = min(cfg["block_cap"], sum(pts[c] for c in ab.caps) * ctx_w.get(ab.block.section, 0.6))
    blocks.sort(key=lambda b: b.raw_points, reverse=True)
    card.ai_blocks = blocks
    factors = [1.0, cfg["second_block_factor"], cfg["third_block_factor"]]

    for ab, factor in zip(blocks, factors):
        w = ctx_w.get(ab.block.section, 0.6) * factor
        earned = 0.0
        for cap, hit in sorted(ab.caps.items(), key=lambda kv: -pts[kv[0]]):
            p = pts[cap] * w
            earned += p
            card.add(category="ai_project_depth", signal=CAPABILITY_LABEL[cap], points=p, quote=hit.quote(),
                     line=hit.line.no, context=f"{ab.block.section}: {ab.block.title[:70]}",
                     note="" if factor == 1 else f"secondary AI project ×{factor}")
        over = earned - cfg["block_cap"] * factor
        if over > 0:
            card.add(category="ai_project_depth", signal="per-project cap", points=-over,
                     context=ab.block.title[:70], note=f"one project is capped at {cfg['block_cap']}")

    if any(b.block.section == "experience" for b in blocks):
        exp = next(b for b in blocks if b.block.section == "experience")
        anchor = next(iter(exp.caps.values()))
        card.add(category="ai_project_depth", signal="AI used in a real job/internship",
                 points=cfg["work_experience_bonus"], quote=anchor.quote(), line=anchor.line.no,
                 context=f"experience: {exp.block.title[:70]}")

    # frameworks that only appear in the skills list: small, capped credit
    in_blocks = " ".join(" ".join(l.text for l in block_lines(resume, b.block)) for b in blocks if b.block.id >= 0).lower()
    skill_only = []
    for h in find(lx.AI_CAPABILITIES["framework"], resume.lines, {"skills", "summary"}, mask=lx.AI_TOOL_USAGE):
        name = h.match.lower()
        if name not in in_blocks and name not in [s.lower() for s in skill_only]:
            skill_only.append(h.match)
            if len(skill_only) <= cfg["skills_framework_cap"] // max(cfg["skills_framework_credit"], 1):
                card.add(category="ai_project_depth", signal=f"{h.match} listed in skills only",
                         points=cfg["skills_framework_credit"], quote=h.quote(), line=h.line.no, context="skills",
                         note="keyword credit only — no project shows it in use")

    # penalties
    thin = [b for b in blocks if b.thin]
    for i, ab in enumerate(thin):
        p = min(cfg["thin_wrapper_penalty"], cfg["thin_wrapper_penalty_cap"] - i * cfg["thin_wrapper_penalty"])
        if p <= 0:
            break
        hit = ab.caps["llm"]
        card.add(category="ai_project_depth", signal="thin LLM-wrapper project", points=-p, quote=hit.quote(),
                 line=hit.line.no, context=ab.block.title[:70],
                 note="calls an LLM/API but shows no retrieval, agents, state, evaluation or data pipeline")
    if blocks and len(thin) == len(blocks):
        card.add(category="ai_project_depth", signal="every AI project is a wrapper", points=-cfg["only_wrappers_extra"])
    tut = [b for b in blocks if b.tutorial and not b.thin]
    for i, ab in enumerate(tut):
        p = min(cfg["tutorial_penalty"], cfg["tutorial_penalty_cap"] - i * cfg["tutorial_penalty"])
        if p <= 0:
            break
        hit = next(iter(ab.caps.values()))
        card.add(category="ai_project_depth", signal="no implementation detail / tutorial-style", points=-p,
                 quote=hit.quote(), line=hit.line.no, context=ab.block.title[:70],
                 note=f"only {ab.block.word_count} words describing it" if ab.block.word_count < cfg["tutorial_min_words"]
                 else "reads like a tutorial/clone")
    card.cap("ai_project_depth", limit)


# ── rubric categories (Python/backend, cloud, engineering depth) ─────────────

def score_rubric(card: ScoreCard, resume: ParsedResume, ctx_w: dict, weights: dict) -> set[str]:
    present: dict[str, tuple[Hit, float]] = {}
    for item in lx.RUBRIC:
        hits = find(item.pattern, resume.lines)
        if not hits:
            continue
        best = max(hits, key=lambda h: ctx_w.get(h.line.section, 0.5))
        present[item.id] = (best, ctx_w.get(best.line.section, 0.5))

    best_in_group: dict[tuple[str, str], tuple[float, str]] = {}
    for item in lx.RUBRIC:
        if item.id not in present:
            continue
        if item.requires and not any(r in present for r in item.requires):
            continue
        hit, w = present[item.id]
        key = (item.category, item.group)
        if key not in best_in_group or item.points * w > best_in_group[key][0]:
            best_in_group[key] = (item.points * w, item.id)

    for (category, _group), (pts, item_id) in best_in_group.items():
        item = lx.RUBRIC_BY_ID[item_id]
        hit, w = present[item_id]
        card.add(category=category, signal=item.label, points=pts, quote=hit.quote(), line=hit.line.no,
                 context=hit.line.section, note="" if w >= 1 else f"×{w} — appears in {hit.line.section}, not in a project/job")
    for cat in ("python_backend", "cloud_fullstack", "engineering_depth"):
        card.cap(cat, weights[cat])
    return set(present)


# ── narrative (strengths / concerns / summary) ───────────────────────────────

def narrate(card: ScoreCard, present: set[str], weights: dict) -> tuple[str, list[str], list[str]]:
    strengths, concerns = [], []
    blocks = card.ai_blocks
    if blocks:
        top = blocks[0]
        caps = [CAPABILITY_LABEL[c] for c in top.caps if c in lx.SUBSTANTIVE_AI]
        summary = f"Strongest AI work — “{top.block.title[:80]}” ({top.block.section})"
        summary += f": {', '.join(caps)}." if caps else ": LLM integration without deeper workflow."
        if len(blocks) > 1:
            summary += f" Plus {len(blocks) - 1} more AI project(s)/role(s)."
        if len(top.substantive) >= 3:
            strengths.append(f"Non-trivial AI system: {', '.join(caps[:4])}")
        if any(b.block.section == "experience" for b in blocks):
            strengths.append("Has applied AI/LLM work in a job or internship")
        if sum(1 for b in blocks if len(b.substantive) >= 2) >= 2:
            strengths.append("Multiple substantive AI projects (breadth)")
    else:
        summary = "No AI project block could be profiled."

    ledger_signals = {e.signal for e in card.ledger if e.points > 0}
    if "FastAPI" in ledger_signals or "Django" in ledger_signals or "Flask" in ledger_signals:
        fw = next(s for s in ("FastAPI", "Django", "Flask") if s in ledger_signals)
        applied = any(e.signal == fw and not e.note for e in card.ledger)
        strengths.append(f"{fw} backend {'used in projects/work' if applied else 'listed'}")
    if card.total("cloud_fullstack") >= 10:
        strengths.append("Deploys end-to-end (containers / cloud / CI)")
    if card.total("engineering_depth") >= 3:
        strengths.append("Shows engineering depth (testing, caching, queues, resilience)")

    if any(b.thin for b in blocks):
        concerns.append(f"{sum(b.thin for b in blocks)} AI project(s) look like thin LLM/API wrappers")
    if blocks and not any(set(b.caps) & {"retrieval", "agents", "framework"} for b in blocks):
        concerns.append("No retrieval, agent or orchestration evidence — AI work is shallow")
    if blocks and not any("evaluation" in b.caps for b in blocks):
        concerns.append("No evaluation / guardrails evidence for AI output quality")
    for need, label in (("fastapi", "FastAPI"), ("postgres", "PostgreSQL"), ("redis", "Redis"),
                        ("docker", "Docker"), ("testing", "testing")):
        if need not in present:
            concerns.append(f"No {label} evidence")
    claimed = [e for e in card.ledger if e.points > 0 and e.note.startswith("×")]
    if len(claimed) >= 4:
        concerns.append(f"{len(claimed)} scored skills appear only in lists, not in projects")
    if not any("python" == e.signal.lower() and not e.note for e in card.ledger):
        concerns.append("Python is listed but not visible inside a project or job")
    return summary, strengths[:5], concerns[:6]


def tier(total: float) -> str:
    return ("Strong shortlist" if total >= 80 else "Shortlist" if total >= 65
            else "Consider" if total >= 50 else "Low fit")
