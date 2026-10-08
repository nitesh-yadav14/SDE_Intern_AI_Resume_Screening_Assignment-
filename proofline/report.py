"""Human-facing views of results.json: a terminal table and a one-file HTML report."""
from __future__ import annotations

import html

SHORT = {"ai_project_depth": "AI", "python_backend": "PY", "cloud_fullstack": "CLD", "github": "GH",
         "engineering_depth": "ENG"}


def render_terminal(result: dict, top: int = 15) -> str:
    s = result["batch_summary"]
    out = [
        "",
        f"  PROOFLINE · {s['total_resumes']} resumes · {s['successfully_parsed']} parsed · "
        f"{s['eligible']} eligible · {s['rejected']} rejected · {s['duplicates']} duplicate · "
        f"{s['failed_unreadable']} unreadable",
        "",
        f"  {'#':>2}  {'candidate':<26} {'score':>5}  {'AI':>4} {'PY':>4} {'CLD':>4} {'GH':>4} {'ENG':>4}  tier",
        "  " + "─" * 78,
    ]
    for c in result["ranking"][:top]:
        b = c["score_breakdown"]
        out.append(f"  {c['rank']:>2}  {(c.get('candidate_name') or c['file'])[:26]:<26} {c['total_score']:>5.1f}  "
                   + " ".join(f"{b[k]:>4.1f}" for k in SHORT) + f"  {c['tier']}")
    return "\n".join(out)


# ── HTML ─────────────────────────────────────────────────────────────────────

def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


CAT_META = [  # key, label, colour var
    ("ai_project_depth", "AI depth", "--c-ai"), ("python_backend", "Python & backend", "--c-py"),
    ("cloud_fullstack", "Cloud & full stack", "--c-cl"), ("github", "GitHub", "--c-gh"),
    ("engineering_depth", "Engineering", "--c-en"),
]
TIER_CLASS = {"Strong shortlist": "t1", "Shortlist": "t2", "Consider": "t3", "Low fit": "t4"}

CSS = """
:root{--bg:#f6f4ef;--panel:#fffdf8;--ink:#1d1b16;--muted:#6b665a;--line:#e4dfd3;--chip:#efebe1;
--c-ai:#d9480f;--c-py:#1c7ed6;--c-cl:#2b8a3e;--c-gh:#7048e8;--c-en:#e8a200;--pos:#2b8a3e;--neg:#c92a2a;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14130f;--panel:#1c1b16;--ink:#ece7da;--muted:#9c968a;
--line:#2e2c25;--chip:#26241e;--c-ai:#ff7a3d;--c-py:#4dabf7;--c-cl:#51cf66;--c-gh:#9775fa;--c-en:#ffc53d;--pos:#69db7c;--neg:#ff6b6b}}
:root[data-theme=dark]{--bg:#14130f;--panel:#1c1b16;--ink:#ece7da;--muted:#9c968a;--line:#2e2c25;--chip:#26241e;
--c-ai:#ff7a3d;--c-py:#4dabf7;--c-cl:#51cf66;--c-gh:#9775fa;--c-en:#ffc53d;--pos:#69db7c;--neg:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--sans)}
.wrap{max-width:1080px;margin:0 auto;padding:40px 16px 80px}
header .k{font:600 12px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--c-ai)}
h1{font-size:clamp(30px,5vw,46px);line-height:1.05;margin:8px 0 10px;letter-spacing:-.02em}
h1 em{font-style:normal;color:var(--c-ai)}
.lede{color:var(--muted);max-width:720px;margin:0}
.meta{font:12px var(--mono);color:var(--muted);margin-top:14px}
h2{font-size:13px;font-family:var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:44px 0 14px;
border-top:1px solid var(--line);padding-top:18px}
.funnel{display:grid;gap:8px}
.fl{display:grid;grid-template-columns:150px 1fr 56px;gap:12px;align-items:center;font-size:14px}
.fl .bar{height:26px;background:var(--chip);border-radius:6px;overflow:hidden}
.fl .bar i{display:block;height:100%;background:var(--ink);border-radius:6px}
.fl:nth-child(4) .bar i{background:var(--c-py)}.fl:nth-child(5) .bar i{background:var(--c-cl)}
.fl b{font:600 15px var(--mono);text-align:right}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.chip{background:var(--chip);border-radius:99px;padding:4px 12px;font-size:13px}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--muted);margin-bottom:12px}
.legend span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:var(--c)}
.tools{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.tools input,.tools select{font:inherit;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
.tools input{flex:1;min-width:200px}
details.cand{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin-bottom:10px}
details.cand[open]{box-shadow:0 6px 24px rgba(0,0,0,.06)}
summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:44px minmax(0,1.3fr) minmax(0,2fr) 64px;
gap:14px;align-items:center;padding:14px 16px}
summary::-webkit-details-marker{display:none}
.rk{font:700 20px var(--mono);color:var(--muted)}
.nm{font-weight:650;font-size:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sub{font-size:12px;color:var(--muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.pill{font:600 11px var(--mono);padding:2px 8px;border-radius:99px;text-transform:uppercase;letter-spacing:.06em}
.t1{background:var(--c-cl);color:#fff}.t2{background:var(--c-py);color:#fff}.t3{background:var(--c-en);color:#1d1b16}.t4{background:var(--chip);color:var(--muted)}
.stack{display:flex;height:14px;border-radius:4px;overflow:hidden;background:var(--chip)}
.stack i{display:block;height:100%;background:var(--c)}
.tot{font:700 26px var(--mono);text-align:right;letter-spacing:-.03em}
.body{padding:4px 18px 18px;border-top:1px dashed var(--line)}
.sum{margin:14px 0 6px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:12px 0}
.cols h4{margin:0 0 6px;font:600 12px var(--mono);text-transform:uppercase;letter-spacing:.1em}
.cols ul{margin:0;padding-left:18px}.good h4{color:var(--pos)}.bad h4{color:var(--neg)}
.brk{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:14px 0}
.brk div{background:var(--chip);border-radius:8px;padding:8px 10px;border-top:3px solid var(--c)}
.brk b{display:block;font:700 18px var(--mono)}.brk span{font-size:12px;color:var(--muted)}
table.ledger{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
.ledger td{border-top:1px solid var(--line);padding:7px 6px;vertical-align:top}
.ledger td.p{font:600 13px var(--mono);text-align:right;white-space:nowrap;width:62px}
.ledger td.p.pos{color:var(--pos)}.ledger td.p.neg{color:var(--neg)}
.ledger .sig{font-weight:600}.ledger .ctx{color:var(--muted);font-size:12px}
.ledger q{font-family:var(--mono);font-size:12px;color:var(--ink);background:var(--chip);padding:1px 4px;border-radius:4px;quotes:"“" "”"}
.ledger tr.cat td{background:var(--chip);font-weight:650;border-top:2px solid var(--line)}
.ledger tr.cat td.p{font-size:15px}
.scroll{overflow-x:auto}
.ledger q{overflow-wrap:anywhere}
.ledger .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--c);margin-right:6px}
.check{font:12px var(--mono);color:var(--muted);margin-top:10px}
.gh{font-size:13px;color:var(--muted);margin:6px 0}
table.rej{width:100%;border-collapse:collapse;font-size:14px;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.rej th{text-align:left;font:600 11px var(--mono);text-transform:uppercase;letter-spacing:.1em;color:var(--muted);padding:10px 12px}
.rej td{border-top:1px solid var(--line);padding:10px 12px;vertical-align:top}
.rej td:first-child{font-weight:600}
body{overflow-wrap:break-word}
.how{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.how div{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:14px}
.how b{display:block;margin-bottom:4px}
.theme{position:fixed;top:14px;right:14px;font:12px var(--mono);background:var(--panel);color:var(--ink);border:1px solid var(--line);
border-radius:99px;padding:6px 12px;cursor:pointer}
@media (max-width:720px){summary{grid-template-columns:34px 1fr 56px}summary .stack{grid-column:2/4}
.cols,.brk{grid-template-columns:1fr 1fr}.fl{grid-template-columns:100px 1fr 44px}}
"""

JS = """
const q=document.getElementById('q'),t=document.getElementById('tier');
function f(){const s=q.value.toLowerCase(),v=t.value;let n=0;document.querySelectorAll('details.cand').forEach(d=>{
const ok=(!s||d.dataset.s.includes(s))&&(!v||d.dataset.t===v);d.style.display=ok?'':'none';if(ok)n++});
document.getElementById('cnt').textContent=n+' shown'}
q.addEventListener('input',f);t.addEventListener('change',f);
document.getElementById('theme').onclick=()=>{const r=document.documentElement,
d=r.dataset.theme==='dark'||(!r.dataset.theme&&matchMedia('(prefers-color-scheme: dark)').matches);r.dataset.theme=d?'light':'dark'};
document.getElementById('expand').onclick=()=>{const all=[...document.querySelectorAll('details.cand')].filter(d=>d.style.display!=='none');
const open=all.some(d=>!d.open);all.forEach(d=>d.open=open)};
"""


def _stack(b: dict) -> str:
    return "".join(f'<i style="width:{b[k]:.2f}%;--c:var({c})" title="{lbl}: {b[k]:g}"></i>' for k, lbl, c in CAT_META)


def _ledger(c: dict) -> str:
    rows = []
    for key, label, col in CAT_META:
        evs = [e for e in c.get("evidence_ledger", []) if e["category"] == key]
        sub = c["score_breakdown"][key]
        rows.append(f'<tr class="cat"><td class="p">{sub:g}</td><td><span class="dot" style="--c:var({col})"></span>'
                    f'{_e(label)} <span class="ctx">— {len(evs)} ledger line(s)</span></td></tr>')
        for ev in evs:
            p = ev["points"]
            cls = "pos" if p > 0 else "neg"
            quote = f'<q>{_e(ev["quote"])}</q>' if ev.get("quote") else ""
            ctx = " · ".join(x for x in (ev.get("context", ""), ev.get("note", "")) if x)
            rows.append(f'<tr><td class="p {cls}">{p:+.2f}</td><td><span class="sig">{_e(ev["signal"])}</span> '
                        f'<span class="ctx">{_e(ctx)}</span>{"<br>" + quote if quote else ""}</td></tr>')
    return '<div class="scroll"><table class="ledger">' + "".join(rows) + "</table></div>"


def _candidate(c: dict) -> str:
    b = c["score_breakdown"]
    gh = c.get("github") or {}
    gh_badge = {"ok": "GitHub ✓", "no_profile": "no GitHub"}.get(gh.get("status"), f"GitHub: {gh.get('status', '—')}")
    llm = c.get("llm_review") or {}
    llm_line = ""
    if llm.get("status") in ("ok", "cached"):
        llm_line = (f'<p class="gh">LLM second review ({_e(llm.get("provider"))}): adjustment {llm.get("applied_adjustment", 0):+g}, '
                    f'{llm.get("verified_quotes", 0)} verified / {llm.get("rejected_quotes", 0)} rejected quotes. {_e(llm.get("detail", ""))}</p>')
    elif llm.get("status") == "failed":
        llm_line = f'<p class="gh">LLM review failed — rule-based score kept ({_e(llm.get("detail"))})</p>'
    search = " ".join([c.get("candidate_name") or "", c["file"], *c.get("matched_skills", [])]).lower()
    ledger_sum = round(sum(e["points"] for e in c.get("evidence_ledger", [])), 1)
    brk = "".join(f'<div style="--c:var({col})"><b>{b[k]:g}</b><span>{lbl} / {w}</span></div>'
                  for (k, lbl, col), w in zip(CAT_META, (40, 30, 15, 10, 5)))
    return f"""
<details class="cand" data-s="{_e(search)}" data-t="{_e(c['tier'])}">
<summary><span class="rk">{c['rank']:02d}</span>
<span><div class="nm">{_e(c.get('candidate_name') or c['file'])}</div>
<div class="sub"><span class="pill {TIER_CLASS[c['tier']]}">{_e(c['tier'])}</span><span>{_e(c['file'])}</span>
<span>· {gh_badge}</span><span>· confidence {_e(c.get('confidence'))}</span></div></span>
<span class="stack">{_stack(b)}</span><span class="tot">{c['total_score']:g}</span></summary>
<div class="body">
<p class="sum">{_e(c.get('project_summary'))}</p>
<div class="brk">{brk}</div>
<div class="cols"><div class="good"><h4>Strengths</h4><ul>{''.join(f'<li>{_e(s)}</li>' for s in c.get('strengths', [])) or '<li>—</li>'}</ul></div>
<div class="bad"><h4>Concerns</h4><ul>{''.join(f'<li>{_e(s)}</li>' for s in c.get('concerns', [])) or '<li>—</li>'}</ul></div></div>
<p class="gh">{_e(c.get('github_summary'))}</p>{llm_line}
<h4 style="margin:16px 0 0;font:600 12px var(--mono);text-transform:uppercase;letter-spacing:.1em">Evidence ledger</h4>
{_ledger(c)}
<p class="check">Σ ledger = {ledger_sum:g} = total score {c['total_score']:g} {'✓' if abs(ledger_sum - c['total_score']) < 0.2 else '✗'}
· skills: {_e(', '.join(c.get('matched_skills', [])))}</p>
</div></details>"""


def render_html(result: dict) -> str:
    s = result["batch_summary"]
    m = result["meta"]
    total = max(1, s["total_resumes"])
    strong = s["tiers"].get("Strong shortlist", 0)
    funnel = [("Resumes in", s["total_resumes"]), ("Parsed", s["successfully_parsed"]),
              ("Passed hard filter", s["eligible"]), ("Shortlist or better", strong + s["tiers"].get("Shortlist", 0)),
              ("Strong shortlist", strong)]
    funnel_html = "".join(f'<div class="fl"><span>{lbl}</span><span class="bar"><i style="width:{100 * n / total:.1f}%"></i></span><b>{n}</b></div>'
                          for lbl, n in funnel)
    reasons = "".join(f'<span class="chip">{_e(k)} · {v}</span>' for k, v in s["rejection_reasons"].items())
    gh = "".join(f'<span class="chip">GitHub {_e(k)} · {v}</span>' for k, v in s["github_enrichment"].items())
    legend = "".join(f'<span style="--c:var({col})">{lbl}</span>' for _, lbl, col in CAT_META)
    cands = "".join(_candidate(c) for c in result["ranking"])
    rej_rows = "".join(
        f'<tr><td>{_e(c.get("candidate_name") or "—")}<div class="sub">{_e(c["file"])}</div></td>'
        f'<td>{"<br>".join(_e(r) for r in c.get("rejection_reasons", []))}</td>'
        f'<td class="sub">{_e(", ".join(c.get("matched_skills", [])[:8]))}</td></tr>' for c in result["rejected"])
    fail_rows = "".join(f'<tr><td>{_e(c["file"])}</td><td colspan="2">{_e(c.get("error"))}</td></tr>' for c in result["failed"])
    top = result["ranking"][0] if result["ranking"] else None
    headline = (f'<em>{s["eligible"]}</em> of {s["total_resumes"]} pass the hard filter. '
                f'<em>{strong}</em> are a strong shortlist.')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Proofline Screening Report</title><style>{CSS}</style></head><body>
<button class="theme" id="theme">◐ theme</button>
<div class="wrap">
<header><div class="k">Proofline · evidence-ledger screening</div>
<h1>{headline}</h1>
<p class="lede">Every point below is backed by a line quoted from the resume. A skill used inside a project or job earns full credit;
the same word in a skills list earns a fraction. Expand any candidate to audit their ledger — it always sums to their score.</p>
<div class="meta">generated {_e(m['generated_at'])} · {m['runtime_seconds']}s · LLM: {_e(m['llm'])} · GitHub: {_e(m['github'])}
{f"· top candidate: {_e(top.get('candidate_name'))} ({top['total_score']:g})" if top else ""}</div></header>

<h2>Funnel</h2><div class="funnel">{funnel_html}</div>
<div class="chips">{reasons}{gh}</div>

<h2>Ranked shortlist</h2>
<div class="legend">{legend}</div>
<div class="tools"><input id="q" placeholder="Filter by name or skill — e.g. langgraph, fastapi"><select id="tier">
<option value="">All tiers</option><option>Strong shortlist</option><option>Shortlist</option><option>Consider</option><option>Low fit</option></select>
<button class="chip" id="expand" style="border:0;cursor:pointer">expand / collapse</button><span class="chip" id="cnt">{len(result['ranking'])} shown</span></div>
{cands}

<h2>Rejected at the hard filter ({len(result['rejected'])})</h2>
<div class="scroll"><table class="rej"><tr><th>Candidate</th><th>Why</th><th>Skills seen</th></tr>{rej_rows}{fail_rows}</table></div>

<h2>How the score is built</h2>
<div class="how">
<div><b>1 · Hard gate (rules, no LLM)</b>Python in skills/projects/work <i>and</i> an AI anchor (LLM, RAG, agents, framework) inside a project or job entry.
Skills-list-only AI and AI <i>coding assistants</i> (Copilot, Cursor) don't count.</div>
<div><b>2 · AI depth, per project</b>Each project is profiled for capabilities — retrieval, agents/tools, framework, state, evaluation,
data pipeline, backend, shipped impact. Best project counts fully, the next ones at 30% / 10%.</div>
<div><b>3 · Penalties are ledger lines</b>Thin LLM wrappers (an API call with no retrieval, tools, state, eval or pipeline) and
tutorial-style entries subtract points with the quote that triggered it.</div>
<div><b>4 · Context-weighted rubric</b>Backend, cloud and engineering signals earn full points in projects/jobs, 40% in a skills list,
25% in certifications — so keyword lists can't win.</div>
<div><b>5 · GitHub, max 10</b>Recency of latest original push (0–5) + recently maintained Python/AI repos (0–5). Missing or private
GitHub is recorded, never fatal.</div>
<div><b>6 · Optional LLM reviewer</b>Schema-validated, may move AI depth by ±6 at most, and every quote it cites is checked against
the resume — invented quotes void its adjustment.</div>
</div>
</div><script>{JS}</script></body></html>"""
