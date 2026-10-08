"""Regenerate the README results table and docs/TECHNICAL_REPORT.pdf from output/results.json.

    python scripts/build_docs.py        (run after main.py)

PDF export uses Playwright if installed (pip install playwright && playwright install chromium);
otherwise docs/technical_report.html is written and can be printed to PDF from any browser.
"""
import html, json, re, sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "output/results.json").read_text(encoding="utf-8"))
S = R["batch_summary"]
e = lambda x: html.escape(str(x if x is not None else ""))
CATS = ["ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"]

# ── README table ─────────────────────────────────────────────────────────────
rows = ["```", "$ python main.py --input ./resumes --output ./output/results.json", "",
        f"  PROOFLINE · {S['total_resumes']} resumes · {S['successfully_parsed']} parsed · {S['eligible']} eligible · "
        f"{S['rejected']} rejected · {S['duplicates']} duplicate · {S['failed_unreadable']} unreadable", "",
        f"   #  {'candidate':<26} {'score':>5}  {'AI':>4} {'PY':>4} {'CLD':>4} {'GH':>4} {'ENG':>4}  tier",
        "  " + "─" * 78]
for c in R["ranking"][:10]:
    b = c["score_breakdown"]
    rows.append(f"  {c['rank']:>2}  {(c.get('candidate_name') or c['file'])[:26]:<26} {c['total_score']:>5.1f}  "
                + " ".join(f"{b[k]:>4.1f}" for k in CATS) + f"  {c['tier']}")
rows.append(f"  …   (+{len(R['ranking']) - 10} more eligible, {S['rejected']} rejected with reasons — see output/)")
rows.append("```")
readme = (ROOT / "README.md").read_text(encoding="utf-8")
readme = re.sub(r"<!-- RESULTS:START -->.*<!-- RESULTS:END -->",
                lambda m: "<!-- RESULTS:START -->\n" + "\n".join(rows) + "\n<!-- RESULTS:END -->", readme, flags=re.S)
readme = re.sub(r"\d+ of the 50 resumes never reach scoring", f"{S['rejected'] + S['duplicates']} of the {S['total_resumes']} resumes never reach scoring", readme)
(ROOT / "README.md").write_text(readme, encoding="utf-8")

# ── Technical report ─────────────────────────────────────────────────────────
by_file = {c["file"]: c for c in R["ranking"] + R["rejected"]}
top = R["ranking"][0]
wrap = next((c for c in R["ranking"] if any(x["signal"] == "every AI project is a wrapper" for x in c["evidence_ledger"])),
            next((c for c in R["ranking"] if any(x["signal"] == "thin LLM-wrapper project" for x in c["evidence_ledger"])), None))


def ledger_rows(c, cats=("ai_project_depth",), limit=9, with_penalties=False):
    out = []
    evs = [x for x in c["evidence_ledger"] if x["category"] in cats]
    if with_penalties:
        evs = [x for x in evs if x["points"] > 0 and x["signal"] != "floor"][:3] + [x for x in evs if x["points"] < 0 and "cap" not in x["signal"]]
    for ev in evs[:limit]:
        cls = "pos" if ev["points"] > 0 else "neg"
        out.append(f'<tr><td class="p {cls}">{ev["points"]:+.1f}</td><td><b>{e(ev["signal"])}</b>'
                   f'{" — <q>" + e(ev["quote"][:118]) + "</q>" if ev.get("quote") else ""}'
                   f'{" <i>" + e(ev["note"][:80]) + "</i>" if ev.get("note") else ""}</td></tr>')
    return "".join(out)


rej_examples = []
for f, why in [("candidate_11.pdf", "Built a real RAG platform — but in React/Supabase/Node; no Python anywhere."),
               ("candidate_34.pdf", "Python backend dev whose only 'AI' is using Claude Code / AI tools to code."),
               ("candidate_45.pdf", "AI terms only in the skills list; no project uses them."),
               ("candidate_21.pdf", "Python + CNN image classifier on Hugging Face — classical ML, no LLM/agentic work."),
               ("candidate_32.pdf", "Solid LLM product (BullMQ, schema retries) — but Node.js only.")]:
    c = by_file.get(f)
    if c and c.get("status") != "eligible":
        rej_examples.append(f"<tr><td><b>{e(c.get('candidate_name'))}</b><br><span class=m>{f}</span></td>"
                            f"<td>{e(' / '.join(c['rejection_reasons']))}</td><td>{e(why)}</td></tr>")

rank_rows = "".join(
    f"<tr><td>{c['rank']}</td><td>{e(c.get('candidate_name'))}</td><td class=n><b>{c['total_score']:g}</b></td>"
    + "".join(f"<td class=n>{c['score_breakdown'][k]:g}</td>" for k in CATS)
    + f"<td>{e(c['tier'])}</td><td class=m>{e((c.get('github') or {}).get('status', ''))}</td></tr>"
    for c in R["ranking"][:12])

gh = ", ".join(f"{k}: {v}" for k, v in S["github_enrichment"].items())
reasons = "".join(f"<li>{e(k)} — <b>{v}</b></li>" for k, v in S["rejection_reasons"].items())

doc = f"""<!doctype html><html><head><meta charset=utf-8><title>Proofline — Technical Report</title><style>
@page{{size:A4;margin:16mm 15mm 16mm}}
body{{font:10.2pt/1.5 Inter,"Segoe UI",system-ui,sans-serif;color:#1d1b16;margin:0}}
h1{{font-size:26pt;line-height:1.05;margin:0 0 6px;letter-spacing:-.02em}} h1 em{{font-style:normal;color:#d9480f}}
h2{{break-after:avoid;font:700 9pt ui-monospace,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;color:#d9480f;margin:20px 0 8px;
border-top:1.5px solid #1d1b16;padding-top:8px}}
h3{{font-size:11pt;margin:12px 0 4px}}
.k{{font:600 8.5pt ui-monospace,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;color:#6b665a}}
.lede{{font-size:11.5pt;color:#3b382f}} .m{{font:8.5pt ui-monospace,Menlo,monospace;color:#6b665a}}
table{{width:100%;border-collapse:collapse;margin:6px 0 4px;font-size:9pt}} td,th{{border-top:1px solid #e4dfd3;padding:4px 6px;vertical-align:top;text-align:left}}
th{{font:600 7.5pt ui-monospace,monospace;text-transform:uppercase;letter-spacing:.08em;color:#6b665a}}
td.n{{text-align:right;font-family:ui-monospace,monospace}} td.p{{font:600 9pt ui-monospace,monospace;white-space:nowrap;text-align:right;width:40px}}
.pos{{color:#2b8a3e}}.neg{{color:#c92a2a}} q{{font:8.4pt ui-monospace,monospace;background:#f1ede3;padding:0 3px}} i{{color:#6b665a}}
.flow{{display:flex;gap:5px;align-items:stretch;margin:10px 0}} .flow div{{flex:1;border:1.5px solid #1d1b16;border-radius:6px;padding:6px 7px;font-size:8.3pt}}
.flow b{{display:block;font-size:9pt;margin-bottom:2px}} .flow .ar{{flex:0 0 10px;border:0;padding:0;align-self:center;font-weight:700}}
.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:10px 0}} .stats div{{background:#f1ede3;border-radius:6px;padding:7px 9px}}
.stats b{{display:block;font:700 17pt ui-monospace,monospace}} .stats span{{font-size:8pt;color:#6b665a}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .box{{border-left:3px solid #d9480f;padding:2px 0 2px 10px;margin:8px 0}}
ul{{margin:4px 0;padding-left:18px}} li{{margin:2px 0}} .pb{{break-before:page}} code{{font:8.8pt ui-monospace,monospace;background:#f1ede3;padding:0 3px}}
</style></head><body>
<div class=k>SDE Intern · AI Resume Screening Assignment · Technical report · Nitesh Yadav</div>
<h1>Proofline: <em>every point has a receipt.</em></h1>
<p class=lede>A Python pipeline that screens a folder of resumes for an AI/agentic SDE internship. Proofline builds an
<b>evidence ledger</b> (one line per point awarded or deducted, each tied to the resume line that earned it), and the score is the
sum of that ledger. Hard eligibility is rule-based and testable. AI depth is judged per project, thin LLM wrappers are
penalised explicitly, and an optional LLM reviewer may only nudge the score, using quotes that are checked against the resume.</p>

<div class=stats><div><b>{S['total_resumes']}</b><span>resumes in</span></div><div><b>{S['successfully_parsed']}</b><span>parsed (0 crashes)</span></div>
<div><b>{S['eligible']}</b><span>pass hard filter</span></div><div><b>{S['tiers'].get('Strong shortlist', 0) + S['tiers'].get('Shortlist', 0)}</b><span>shortlist or better</span></div>
<div><b>{R['meta']['runtime_seconds']}s</b><span>full batch runtime</span></div></div>

<h2>1 · Architecture</h2>
<div class=flow>
<div><b>① Ingest</b>pypdf vs pdfplumber <i>tournament</i>; link annotations; sections; project blocks</div><div class=ar>→</div>
<div><b>② Hard gate</b>rules only: Python + AI <i>inside a project/job</i></div><div class=ar>→</div>
<div><b>③ Ledger</b>per-project AI profiling; context-weighted rubric; penalties as lines</div><div class=ar>→</div>
<div><b>④ GitHub</b>≤10 pts; cached; bounded threads; circuit breaker</div><div class=ar>→</div>
<div><b>⑤ LLM review</b>optional; schema-validated; ±6 max; quote-verified</div></div>
<p>Modules map 1:1 to stages (<code>ingest.py</code>, <code>eligibility.py</code>, <code>scoring.py</code>, <code>github.py</code>,
<code>llm.py</code>), orchestrated by <code>pipeline.py</code>. All data contracts are Pydantic models (<code>models.py</code>).
Weights, caps, context multipliers and penalties live in <code>proofline.toml</code>. Signal patterns live in <code>lexicon.py</code>
as data, so changing a weight is a config edit and the ledger shows exactly which points moved.</p>
<div class=two><div>
<h3>Ingestion details that mattered on this dataset</h3>
<ul><li><b>Extractor tournament.</b> Some PDFs come out letter-spaced in pypdf (<code>S K I L L S</code>), others glue two columns together in
pdfplumber. Each output is scored for readability and the number of sections it can recognise, and the better one is kept. Here {sum(1 for c in R['ranking'] + R['rejected'] if c.get('parse_meta', {}).get('extractor') == 'pdfplumber')} files picked pdfplumber and the rest pypdf.</li>
<li><b>Hidden GitHub links.</b> Many resumes show only a GitHub <i>icon</i>, so the URL exists only in the PDF link annotations. Reading those
recovers the handle for about 20 candidates who have no github.com text.</li>
<li><b>Word-per-line reflow</b> for justified PDFs, and <code>mailto:</code> links preferred when icon glyphs get glued onto the email address.</li></ul>
</div><div>
<h3>Reliability</h3>
<ul><li>Each file is parsed through <code>safe_read</code>, so a corrupt, empty or image-only PDF becomes a <code>failed</code> entry with a reason instead of an exception.</li>
<li>Duplicates are detected by content hash <i>and</i> email.</li>
<li>Parsing is CPU-bound, so it runs on a bounded process pool: <b>12.5 s → 6.9 s</b> for 50 PDFs on 2 cores.</li>
<li>GitHub and LLM calls use bounded thread pools, on-disk caches and typed failure statuses.</li>
<li><b>19 pytest tests</b> cover eligibility edge cases, ledger arithmetic, penalties, GitHub failure, LLM clamping and hallucination rejection, and a batch containing corrupt and duplicate files.</li></ul>
</div></div>

<h2 class=pb>2 · Hard eligibility: rules, and the evidence has to be applied</h2>
<p>Eligibility never involves the LLM. <b>Python</b> must appear in skills, projects, work or the summary. A Python-only framework (Django/FastAPI)
also counts, but a certification such as "Crash Course on Python" alone does not. <b>AI</b> must appear <i>inside a project or job entry</i>
as a real anchor (LLM, RAG, embeddings/vector search, an agent framework). Ambiguous words (agent, transformer, chunking, Hugging Face) only count
next to a strong AI term. Two choices go further than plain keyword matching:</p>
<div class=box><b>AI listed only in skills is rejected.</b> The requirement is a <i>project</i> showing AI work, so a skills list is a claim, not evidence.<br>
<b>Using AI coding assistants is not AI engineering.</b> Phrases such as "GitHub Copilot", "Cursor" and "Claude Code" are masked before AI signals are searched for.</div>
<p>Rejection reasons in this batch:</p><ul>{reasons}</ul>
<table><tr><th style="width:24%">Candidate</th><th style="width:38%">Recorded reason</th><th>Why it's the right call</th></tr>{''.join(rej_examples)}</table>
<p class=m>JavaScript, Java and React are never a reason to reject. Several eligible candidates are full-stack and also meet the Python + AI requirement.</p>

<h2>3 · Scoring: the ledger is the score</h2>
<div class=two><div>
<h3>AI depth (40) is judged per project</h3>
<p>Each project or job block is profiled for capabilities:
retrieval 7 · agents/tools 8 · framework 5 · state/memory 4 · evaluation 5 · data pipeline 3 · wired into a backend 4 · LLM 3 · shipped/measured 3.
A single project is capped at 28. The best project counts in full and the next ones at ×0.3 and ×0.1, so breadth can't stand in for depth.
Applied AI in a real job adds +3. A framework that appears only in the skills list earns 1 point, capped at 3.</p>
<h3>Penalties are ledger lines, with the quote that triggered them</h3>
<ul><li><b>Thin wrapper</b> (an LLM call with no retrieval, tools, state, evaluation or pipeline): −6 per project, up to −12, and another −4 if every AI project is a wrapper.</li>
<li><b>Tutorial-style</b> (under 18 words of description, or clone/tutorial wording): −3 each.</li></ul>
</div><div>
<h3>Context weighting does "evidence over keywords"</h3>
<table><tr><th>Where the match is</th><th>Multiplier</th></tr><tr><td>experience / project entry</td><td class=n>×1.0</td></tr>
<tr><td>unrecognised section</td><td class=n>×0.6</td></tr><tr><td>summary</td><td class=n>×0.5</td></tr>
<tr><td>skills list</td><td class=n>×0.4</td></tr><tr><td>certifications / education</td><td class=n>×0.25</td></tr></table>
<p>So "FastAPI" in a project bullet earns 7 points, and in a skills list 2.8, with a note on the ledger line saying why. Python & backend (30),
cloud & full stack (15) and engineering depth (5) are rubric items grouped so they can't double-count (FastAPI + Flask + Django → only the best one counts).
React/Next.js earn points only when a backend is also present. Category caps are explicit negative lines, so <b>Σ ledger = total</b> always.</p>
</div></div>

<h3>Excerpt: #{top['rank']} {e(top.get('candidate_name'))} ({top['total_score']:g}), AI depth ledger</h3>
<table>{ledger_rows(top, limit=7)}</table>
{f'''<h3>Excerpt: a penalised wrapper, {e(wrap.get('candidate_name'))} ({wrap['total_score']:g})</h3><table>{ledger_rows(wrap, limit=8, with_penalties=True)}</table>''' if wrap else ''}

<h2>4 · GitHub enrichment and LLM review</h2>
<div class=two><div>
<h3>GitHub (max 10, never a gate)</h3>
<ul><li><b>Activity 0–5:</b> days since the last push to an original repo (forks and archives excluded): ≤30d 5 · ≤90d 4 · ≤180d 3 · ≤365d 2 · older 1.</li>
<li><b>Relevance 0–5:</b> 1.5 points per original repo pushed in the last 12 months that is Python/Jupyter or AI-flavoured by name, description or topics.</li>
<li>2 calls per user, cached on disk, on a bounded thread pool, and only for eligible candidates. Rate limits, 404s and network errors become a
recorded status. A circuit breaker stops further calls once the API is down. The token is read from <code>GITHUB_TOKEN</code>.</li>
<li>This run: {e(gh)}.</li></ul>
</div><div>
<h3>LLM (optional, with tight limits)</h3>
<ul><li>Reviews only the AI blocks the rules found and returns a Pydantic-validated <code>LLMVerdict</code> (depth label, evidence quote and adjustment per project).</li>
<li>The adjustment is clamped to <b>±6</b>. Eligibility and the other categories can't be changed.</li>
<li><b>Hallucination guard:</b> every quote must fuzzy-match the resume. An adjustment backed only by invented quotes is dropped and counted.</li>
<li>A malformed reply gets one repair retry. After that, or on a provider error, the review is marked <code>failed</code> and the rule-based score stands.</li>
<li>One OpenAI-compatible adapter covers OpenAI, Groq, Gemini, OpenRouter and Ollama. Results are cached by model, prompt version and resume hash.</li>
<li>The shipped results are rule-based, so anyone who clones the repo gets the same ranking without an API key.</li></ul>
</div></div>

<h2>5 · Results (top 12 of {S['eligible']} eligible)</h2>
<table><tr><th>#</th><th>Candidate</th><th>Total</th><th>AI/40</th><th>Py/30</th><th>Cloud/15</th><th>GH/10</th><th>Eng/5</th><th>Tier</th><th>GitHub</th></tr>{rank_rows}</table>
<p class=m>Full output: <code>output/results.json</code> (ranking with ledgers, rejected candidates with reasons, failed files, batch summary) and <code>output/report.html</code> (interactive report).</p>

<div style="break-inside:avoid"><h2>6 · Trade-offs and next steps</h2>
<ul><li><b>Known blind spot:</b> rules can't tell that an LLM call wired into a CI failure hook is real product logic. That is the gap the bounded LLM reviewer is meant to cover, and the reason it is limited to adjusting AI depth.</li>
<li><b>Calibration set:</b> hand-label about 15 resumes, tune the capability weights, and make precision@10 a test.</li>
<li><b>Layout-aware extraction</b> (pymupdf blocks, with an LLM extraction fallback) for two-column PDFs that still glue words together.</li>
<li><b>Resume-to-code consistency:</b> read the top repo's dependency files to confirm that the LangGraph/RAG claimed on the resume exists in code.</li>
<li><b>Reviewer feedback:</b> let recruiters flag wrong ledger lines in the HTML report, and turn those flags into lexicon fixes and regression tests.</li></ul>
<p class=m>Run: <code>pip install -r requirements.txt && python main.py --input ./resumes --output ./output/results.json</code> · Tests: <code>pytest -q</code></p></div>
</body></html>"""
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/technical_report.html").write_text(doc, encoding="utf-8")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto((ROOT / "docs/technical_report.html").as_uri())
        pg.pdf(path=str(ROOT / "docs/TECHNICAL_REPORT.pdf"), format="A4", print_background=True)
        b.close()
    print("wrote docs/TECHNICAL_REPORT.pdf")
except Exception as exc:  # playwright optional
    print(f"PDF skipped ({type(exc).__name__}); open docs/technical_report.html and print to PDF")
print("updated README.md and docs/technical_report.html")
