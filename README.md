# Proofline — evidence-ledger resume screening

**Author:** Nitesh Yadav · [github.com/nitesh-yadav14](https://github.com/nitesh-yadav14) · SDE Intern (AI) assignment

> **Every point has a receipt.** Proofline screens a folder of resumes for an AI/agentic SDE internship.
> Instead of producing a score and then explaining it, it builds an **evidence ledger** first: one line per point
> awarded or deducted, each tied to the resume line that earned it. The final score is just the sum of the ledger,
> and the tests check that it always adds up.

<!-- RESULTS:START -->
```
$ python main.py --input ./resumes --output ./output/results.json

  PROOFLINE · 50 resumes · 50 parsed · 32 eligible · 18 rejected · 0 duplicate · 0 unreadable

   #  candidate                  score    AI   PY  CLD   GH  ENG  tier
  ──────────────────────────────────────────────────────────────────────────────
   1  Prathamesh                 100.0  40.0 30.0 15.0 10.0  5.0  Strong shortlist
   2  Jyandeep Baishya            89.4  39.4 28.0  9.5 10.0  2.5  Strong shortlist
   3  Prajwal A S                 85.5  40.0 29.0  6.0  9.0  1.5  Strong shortlist
   4  Abhinav Mishra              82.3  35.4 24.4  9.5 10.0  3.0  Strong shortlist
   5  Raj Thumar                  81.5  36.7 29.0  9.3  2.0  4.5  Strong shortlist
   6  Sumaiya Sultana             80.7  32.6 21.6 12.5 10.0  4.0  Strong shortlist
   7  Yash Maini                  80.3  27.8 28.0 10.5 10.0  4.0  Strong shortlist
   8  V Sree Raghu Vardhan        79.8  28.0 29.4 11.9  5.5  5.0  Shortlist
   9  Thejeshwaar Paasila         78.4  34.3 27.0 11.6  3.0  2.5  Shortlist
  10  Vaibhav Wakde               77.9  34.0 23.0  8.6  9.5  2.8  Shortlist
  …   (+22 more eligible, 18 rejected with reasons — see output/)
```
<!-- RESULTS:END -->

Outputs:
- **`output/results.json`**: the machine-readable result. It has a batch summary, ranked eligible candidates with their full ledger, rejected candidates with reasons, and unreadable files with the error.
- **`output/report.html`**: a single offline HTML file with the funnel, a filterable ranking with stacked score bars, and an expandable ledger for every candidate.

---

## Quick start

```bash
git clone <this-repo> && cd <this-repo>
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py --input ./resumes --output ./output/results.json     # full run (GitHub on)
python main.py --no-github                                          # fully offline
python main.py --llm                                                # + LLM second reviewer (needs LLM_API_KEY)
pytest -q                                                           # 19 tests, < 1 s
```

Optional: run `cp .env.example .env`. Then add a `GITHUB_TOKEN`, which raises the GitHub API limit from 60 to 5,000 requests per hour, and/or an `LLM_API_KEY`. You can also run it as an HTTP API with `pip install fastapi uvicorn && uvicorn proofline.api:app`. That gives you `POST /screen`, `GET /results` and `GET /results/{rank}`.

Requires Python ≥ 3.11 (it uses `tomllib`). Input can be PDF, DOCX or TXT.

---

## How it works

```
 resumes/ ──► ① ingest ──────► ② hard gate ──────► ③ evidence ledger ──► ④ GitHub ──► ⑤ LLM review ──► rank
              extractor         rules only:          per-project AI         ≤10 pts,     optional,
              tournament,       Python + applied     profiling, context-    cached,      ±6 max,
              hidden links,     AI evidence          weighted rubric,       bounded      quote-verified
              sections, blocks                       penalties as lines     threads
```

| Stage | What makes it different |
|---|---|
| **① Ingest** (`ingest.py`) | **Extractor tournament.** `pypdf` and `pdfplumber` each extract the text. Each output is scored for readability (letter-spaced text, glued words, one-word-per-line output) and for how many resume sections it can recognise, and the better one wins. **Hidden links.** About 20 of the 50 resumes link GitHub only through an *icon*, so the URL lives in the PDF's link annotations, which Proofline reads. Section headings are matched by vocabulary, not position ("Work History", "Internships" → experience). Project and job entries are split into **blocks**, so evidence can be judged per project. |
| **② Hard gate** (`eligibility.py`) | Pure rules, with no LLM involved. Python must be a working skill. AI evidence must appear *inside a project or job entry*. AI words that only sit in the skills list are rejected, with a reason that says so. Using **AI coding assistants** (Copilot, Cursor, Claude Code) is masked out: it isn't building AI systems. |
| **③ Ledger** (`scoring.py`) | AI depth is profiled **per project** across 9 capabilities. A project that only calls an LLM API is flagged as a **thin wrapper** and gets a negative ledger line. Backend, cloud and engineering skills earn full points when they appear in a project or job, ×0.4 in a skills list and ×0.25 in certifications. |
| **④ GitHub** (`github.py`) | 2 API calls per user, cached on disk, run on a bounded thread pool. Any failure (rate limit, 404, network) becomes a *status* on the candidate. A circuit breaker stops further calls once the API is down. |
| **⑤ LLM** (`llm.py`) | An optional second reviewer behind a `Reviewer` protocol. Its output is Pydantic-validated, a malformed reply gets one repair retry, and its quotes are checked against the resume. |

---

## Design Decisions

### Filtering strategy: rules only, and evidence has to be applied
The hard gate is deterministic and has no LLM in it. That makes it **testable**: there are unit tests for "JS-only with RAG → reject", "Python without AI → reject", "AI only in skills → reject" and "Copilot user → reject". It also makes it **cheap**: 18 of the 50 resumes never reach scoring or GitHub.

- **Python** counts if it appears in skills, projects, work or the summary. Python-only frameworks (Django, FastAPI…) also count when the word "Python" is missing. A Python mention that exists *only* in a certification ("Crash Course on Python") does not.
- **AI** counts only if an AI anchor (an LLM, RAG/retrieval, embeddings, an agent framework) appears **inside a project or job entry**. Ambiguous words ("agent", "transformer", "chunking", "Hugging Face") count only when a strong AI term is nearby. Classical ML on its own (CNN, scikit-learn) is rejected with its own reason, because the role asks for LLM/agentic work.
- JavaScript, Java and React are never a reason to reject. Several eligible candidates use them.

### Scoring strategy: the ledger is the score
- **Explainability comes first.** Every ledger line has `category, signal, points, quote, line, context, note`. Caps and floors are explicit ledger lines too, so `Σ ledger == total_score` always holds. The HTML report shows ✓ next to every candidate.
- **AI depth (40) is judged per project, not per resume.** Each project or job block is profiled for *retrieval, agents/tools, framework, state/memory, evaluation, data pipeline, backend integration, LLM, shipped impact*. The best project counts in full and the next ones at 30% and 10%, so breadth helps but can't replace depth. Applied AI in a real job adds +3. A framework that only appears in a skills list earns 1 point, capped at 3.
- **Penalties.** A *thin LLM wrapper* (an LLM call with no retrieval, tools, state, evaluation or pipeline) costs −6 per project, up to −12, and another −4 if *every* AI project is a wrapper. A *tutorial-style* entry (under 18 words of description, or clone/tutorial wording) costs −3.
- **Context weights do the "evidence over keywords" work.** "FastAPI" in a project bullet is worth 7 points; in a skills list it is worth 2.8, with a note on the ledger line explaining why.
- **Config, not code.** All weights, caps, context multipliers and penalties live in `proofline.toml`. Signal patterns live in `lexicon.py` as data.
- **Tiers:** Strong shortlist ≥ 80, Shortlist ≥ 65, Consider ≥ 50, otherwise Low fit.
- **Confidence** (`high` / `medium` / `low`) tells a reviewer how much of a score rests on applied evidence rather than skill-list claims, and how cleanly the PDF parsed. In other words, which ledgers deserve a human look.

### LLM usage: a bounded second opinion, not the judge
Rules are predictable but miss nuance. For example, an OpenAI log analyser wired into a Jenkins failure hook is real product logic, but the rules see "LLM, no retrieval" and call it a wrapper. LLMs catch that kind of nuance but hallucinate. So the LLM gets a narrow job:
- It reviews only the AI projects the rules already found, and returns a **Pydantic-validated `LLMVerdict`** (depth label per project, an evidence quote, and an adjustment).
- The adjustment is **clamped to ±6** of the 40 AI points. Eligibility is never touched.
- **Quote verification.** Every `evidence_quote` must fuzzy-match the resume text. An adjustment backed only by invented quotes is dropped, and the rejected count is reported.
- If the reply is malformed it gets one repair retry. If that fails, or the provider errors, the review is marked `failed` and the rule-based score stands. Results are cached by (model, prompt version, resume hash).
- Provider-agnostic: there is one `OpenAICompatibleReviewer`, and OpenAI, Groq, Gemini (OpenAI endpoint), OpenRouter and Ollama are all just `LLM_BASE_URL` + `LLM_MODEL`.

The shipped `results.json` was produced **rule-based** (`--llm` off), with the committed GitHub snapshot. That keeps it reproducible: anyone who clones the repo gets the same ranking, with no API key needed.

### GitHub scoring: recency + relevance, failure-tolerant
- **Activity (0–5)** is based on days since the last push to an *original* repo (forks and archives excluded): ≤30 days → 5, ≤90 → 4, ≤180 → 3, ≤365 → 2, older → 1.
- **Relevance (0–5)** gives 1.5 points per original repo pushed in the last 12 months that is Python/Jupyter or AI-flavoured by name, description or topic.
- The username is taken from text *and* link annotations. When a resume only links repos, the repo owner is used.
- **Shipped snapshot.** `cache/github/` holds the public GitHub data used for the shipped `results.json` (taken 2026-10-08), so a fresh clone reproduces the same ranking offline. Delete `cache/github/` to fetch live data.
- Only **eligible** candidates are enriched, which saves API budget. A missing, private or rate-limited profile gives 0 points and a recorded status, and never affects eligibility.

### Other engineering choices
- **Robustness.** Every file goes through `safe_read`, so a corrupt, empty or image-only PDF becomes a `failed` entry with the error. Duplicates are detected by content hash *and* email.
- **Speed.** PDF parsing is CPU-bound, so it runs in a bounded `ProcessPoolExecutor` (`--workers`, default 4). On a 2-core machine that took 50 resumes from 12.5 s to 6.9 s. GitHub and LLM calls use bounded thread pools.
- **Privacy.** Phone numbers are never written to the output. Only name, email and GitHub handle are kept.

---

## If I Had More Time

1. **A labelled calibration set.** Hand-label about 15 resumes as strong, ok or weak and tune the capability weights against them. Precision@10 would become a test, and weight changes would come with a measurable before/after.
2. **LLM extraction for messy layouts.** Two-column and Canva-style PDFs still sometimes glue words ("DesignedscalableSQLdatabase"). The next step is a layout-aware extractor (pymupdf blocks), with LLM structured extraction of project blocks as a fallback when readability is low.
3. **Deeper GitHub signal.** Read the top relevant repo's README and dependency files (`requirements.txt`, `pyproject.toml`) to confirm that the LangGraph/RAG claimed on the resume actually exists in code. The resume-to-code consistency check would become its own ledger line.
4. **A reviewer feedback loop.** Let a recruiter mark a ledger line as wrong in the HTML report, store those overrides, and use them to adjust the lexicon. The overrides would also double as regression tests.

---

## Project layout

```
proofline/
  ingest.py        extraction tournament, link harvesting, sections, project blocks, contact fields
  eligibility.py   hard gate (rules only)
  lexicon.py       every signal pattern + rubric item, as data
  scoring.py       evidence ledger: per-project AI profiling, penalties, rubric, narrative
  github.py        cached, bounded, failure-tolerant GitHub enrichment
  llm.py           Reviewer protocol, OpenAI-compatible adapter, schema validation, quote verification
  pipeline.py      orchestration, dedupe, ranking, batch summary
  report.py        terminal table + self-contained HTML report
  models.py        Pydantic contracts for everything above
  config.py        proofline.toml + env vars (+ tiny .env loader)
  api.py           optional FastAPI wrapper
main.py            CLI
scripts/build_docs.py  refreshes the README table + docs/TECHNICAL_REPORT.pdf from output/results.json
proofline.toml     all weights, caps, context multipliers, penalties
tests/             19 tests: eligibility, scoring, penalties, GitHub, LLM guardrails, batch robustness
output/            results.json + report.html for the provided 50 resumes
docs/              TECHNICAL_REPORT.pdf (5-page design write-up)
```
