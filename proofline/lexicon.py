"""Signal lexicon + rubric items.

Everything the scorer looks for is declared here as data:
  * ``AI_CAPABILITIES`` – what an AI project *does* (retrieval, agents, …).
    Used per project block to judge depth and detect thin wrappers.
  * ``RUBRIC`` – flat rubric items for the non-AI categories. Each item has a
    group; inside a group only the best match counts, so "FastAPI + Flask +
    Django" doesn't triple-dip.

Patterns are compiled case-insensitively and matched against one resume line
at a time, which is what lets every point carry a quote.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def _rx(*alts: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{a})" for a in alts), re.IGNORECASE)


# ── Python ────────────────────────────────────────────────────────────────────
PYTHON = _rx(r"\bpython\d?\b")
PYTHON_FRAMEWORKS = _rx(r"\bdjango\b", r"\bfast\s?api\b", r"\bflask\b", r"\bpandas\b", r"\bnumpy\b",
                        r"\bpytorch\b", r"\bpydantic\b", r"\bstreamlit\b")

# ── AI capability families (per-block) ────────────────────────────────────────
AI_CAPABILITIES: dict[str, re.Pattern[str]] = {
    "framework": _rx(r"lang\s?chain", r"lang\s?graph", r"llama\s?-?index", r"google\s+adk", r"\bcrew\s?ai\b",
                     r"\bautogen\b", r"semantic\s+kernel", r"\bhaystack\b", r"\bdspy\b", r"smolagents",
                     r"pydantic[\s-]?ai", r"\bmcp\b", r"model\s+context\s+protocol", r"openai\s+agents\s+sdk",
                     r"\bagno\b", r"\bphidata\b"),
    "retrieval": _rx(r"\brag\b", r"retrieval[\s-]augmented", r"\bembeddings?\b", r"vector\s*(?:db|database|store|search|index)s?",
                     r"semantic\s+search", r"\bfaiss\b", r"\bchroma(?:db)?\b", r"\bpinecone\b", r"\bweaviate\b",
                     r"\bqdrant\b", r"\bmilvus\b", r"pgvector", r"re-?rank", r"hybrid\s+search", r"\bbm25\b",
                     r"chunking", r"knowledge\s+base"),
    "agents": _rx(r"\bagent(?:s|ic)?\b", r"multi[\s-]agent", r"tool[\s-](?:calling|use|augmented)",
                  r"function[\s-]calling", r"\breact\s+agent", r"planner", r"orchestrat\w*(?!\s+(?:via|with|using|on|through)\s+(?:kubernetes|k8s|docker|helm))",
                  r"autonomous"),
    "state": _rx(r"\bmemory\b", r"state(?:ful)?\b", r"checkpoint\w*", r"conversation\s+history",
                 r"session\s+(?:state|memory)", r"human[\s-]in[\s-]the[\s-]loop"),
    "evaluation": _rx(r"\bevals?\b", r"evaluation", r"\bragas\b", r"deepeval", r"guardrails?", r"hallucinat\w*",
                      r"llm[\s-]as[\s-](?:a[\s-])?judge", r"langsmith", r"benchmark\w*", r"faithfulness", r"precision@"),
    "llm": _rx(r"\bllms?\b", r"large\s+language\s+models?", r"\bgpt[\s-]?\d*\w*", r"\bopenai\b", r"\bgemini\b",
               r"\bclaude\b", r"\banthropic\b", r"\bgroq\b", r"\bllama\s?\d?", r"\bmistral\b", r"\bollama\b",
               r"gen(?:erative)?\s?ai", r"prompt\s+engineering", r"hugging\s?face", r"\btransformers?\b", r"\bbert\b"),
    "data_pipeline": _rx(r"ingestion", r"(?<!cd )(?<!ment )(?<!build )pipelines?", r"\betl\b", r"pars(?:e|ing|er)", r"\bocr\b", r"pre-?process\w*",
                         r"structured\s+(?:output|data)", r"json\s+schema", r"extraction"),
    "product_backend": _rx(r"fast\s?api", r"\bdjango\b", r"\bflask\b", r"rest(?:ful)?\s+api", r"postgres\w*",
                           r"\bredis\b", r"\bdatabase\b", r"websocket", r"backend"),
    "shipped": _rx(r"deployed", r"production", r"\d[\d,]*\+?\s*(?:users|requests|queries|documents|docs|records)",
                   r"\blive\b", r"latency", r"\d+\s?%"),
}
# Capabilities that make an AI block more than "call an LLM API".
SUBSTANTIVE_AI = {"framework", "retrieval", "agents", "state", "evaluation", "data_pipeline"}
# Capabilities that alone qualify a block as an AI block at all.
AI_ANCHORS = {"framework", "retrieval", "agents", "llm"}
# Words that, on their own, are too generic to anchor an AI block.
WEAK_ANCHOR_ONLY = _rx(r"\bagents?\b", r"orchestrat\w*", r"planner", r"autonomous", r"\btransformers?\b",
                       r"hugging\s?face", r"\bbert\b", r"chunking", r"knowledge\s+base", r"re-?rank\w*",
                       r"hybrid\s+search", r"\bbm25\b", r"\bmcp\b")
# Using an AI coding assistant is not building AI systems. These phrases are
# blanked out before any AI signal is searched for.
AI_TOOL_USAGE = _rx(r"claude\s+code", r"github\s+copilot", r"\bcopilot\b", r"\bcursor(?:\s+ai)?\b", r"\bwindsurf\b",
                    r"ai[\s-](?:assisted|powered)\s+(?:development|coding|dev)(?:\s+tools?)?(?:\s*\([^)]*\))?",
                    r"ai\s+(?:coding\s+)?tools?(?:\s*\([^)]*\))?", r"claude\s+ai", r"chatgpt",
                    r"(?:using|with|leveraged?)\s+(?:chatgpt|claude|gemini)\s+(?:for|to)\s+(?:coding|debugging|prototyping)",
                    r"ai\s+development\s+tools?", r"\bcodex\b", r"tools\s*\(\s*cursor[^)]*\)")
TUTORIAL = _rx(r"\btutorial\b", r"\bclone\b", r"follow(?:ed|ing)\s+(?:a|the)\s+course", r"bootcamp\s+project",
               r"guided\s+project", r"\bcodealong\b")
CLASSIC_ML = _rx(r"tensorflow", r"pytorch", r"scikit", r"sklearn", r"\bcnn\b", r"opencv", r"keras", r"xgboost",
                 r"machine\s+learning", r"deep\s+learning")


@dataclass(frozen=True)
class RubricItem:
    id: str
    label: str
    category: str
    group: str
    points: float
    pattern: re.Pattern[str]
    requires: tuple[str, ...] = field(default_factory=tuple)  # other item ids that must also be present


RUBRIC: list[RubricItem] = [
    # ── Python & Backend (cap 30) ─────────────────────────────────────────────
    RubricItem("python", "Python", "python_backend", "python", 10, PYTHON),
    RubricItem("fastapi", "FastAPI", "python_backend", "framework", 7, _rx(r"\bfast\s?api\b")),
    RubricItem("django", "Django", "python_backend", "framework", 6, _rx(r"\bdjango\b")),
    RubricItem("flask", "Flask", "python_backend", "framework", 5, _rx(r"\bflask\b")),
    RubricItem("async", "Async / background work", "python_backend", "async", 4,
               _rx(r"\basync(?:io|hronous)?\b", r"\bcelery\b", r"background\s+(?:tasks?|jobs?|workers?)", r"websockets?",
                   r"\bawait\b", r"concurrent")),
    RubricItem("postgres", "PostgreSQL", "python_backend", "sql", 4, _rx(r"postgre(?:s|sql)\b", r"\bpgvector\b")),
    RubricItem("other_sql", "SQL database", "python_backend", "sql", 2, _rx(r"\bmysql\b", r"\bsqlite\b", r"\bsql\s?server\b")),
    RubricItem("redis", "Redis", "python_backend", "redis", 3, _rx(r"\bredis\b")),
    RubricItem("api_work", "API / backend implementation", "python_backend", "api", 3,
               _rx(r"rest(?:ful)?\s+apis?", r"\bendpoints?\b", r"\bmicroservices?\b", r"\bgraphql\b", r"backend\s+services?")),
    RubricItem("orm", "ORM / data layer", "python_backend", "orm", 1, _rx(r"sqlalchemy", r"\borm\b", r"alembic", r"pydantic")),

    # ── Cloud / Deployment / Full stack (cap 15) ──────────────────────────────
    RubricItem("docker", "Docker", "cloud_fullstack", "containers", 4, _rx(r"\bdocker(?:ized|file)?\b", r"containeri[sz]")),
    RubricItem("k8s", "Kubernetes", "cloud_fullstack", "orchestration", 2, _rx(r"kubernetes", r"\bk8s\b", r"\bhelm\b")),
    RubricItem("gcp", "GCP", "cloud_fullstack", "cloud", 4, _rx(r"\bgcp\b", r"google\s+cloud", r"cloud\s+run", r"vertex\s+ai",
                                                               r"bigquery", r"firebase")),
    RubricItem("aws", "AWS", "cloud_fullstack", "cloud", 3.5, _rx(r"\baws\b", r"\bec2\b", r"\blambda\b", r"\bs3\b", r"bedrock")),
    RubricItem("azure", "Azure", "cloud_fullstack", "cloud", 3.5, _rx(r"\bazure\b")),
    RubricItem("deploy", "Deployment / CI-CD", "cloud_fullstack", "deploy", 3,
               _rx(r"\bdeploy(?:ed|ment|ing)?\b", r"ci\s?/\s?cd", r"github\s+actions", r"\bjenkins\b", r"\bvercel\b",
                   r"\brender\b", r"\bheroku\b", r"\bnginx\b", r"\bterraform\b")),
    RubricItem("react", "React / Next.js (end-to-end)", "cloud_fullstack", "frontend", 3,
               _rx(r"\breact(?:\.?js)?\b(?!\s+agent)", r"next\.?js", r"\bvue\b", r"\bangular\b"),
               requires=("fastapi", "django", "flask", "api_work")),

    # ── Engineering depth (cap 5) ─────────────────────────────────────────────
    RubricItem("testing", "Testing", "engineering_depth", "testing", 1.5,
               _rx(r"\bpytest\b", r"unit\s+tests?", r"integration\s+tests?", r"test\s+coverage", r"\bunittest\b", r"\btdd\b")),
    RubricItem("caching", "Caching", "engineering_depth", "caching", 1, _rx(r"cach(?:e|ing|ed)")),
    RubricItem("queues", "Queues / event-driven", "engineering_depth", "queues", 1,
               _rx(r"\bkafka\b", r"rabbitmq", r"\bcelery\b", r"\bbullmq\b", r"\bsqs\b", r"pub\s?/?\s?sub", r"message\s+queue",
                   r"event[\s-]driven", r"job\s+queue")),
    RubricItem("observability", "Observability", "engineering_depth", "observability", 1,
               _rx(r"\blogging\b", r"monitoring", r"prometheus", r"grafana", r"opentelemetry", r"\bsentry\b", r"langsmith",
                   r"tracing", r"cloudwatch")),
    RubricItem("resilience", "Failure handling / concurrency", "engineering_depth", "resilience", 1,
               _rx(r"\bretr(?:y|ies)\b", r"rate[\s-]limit\w*", r"circuit\s+breaker", r"idempoten\w*", r"fallback",
                   r"concurren\w*", r"fault[\s-]toleran\w*", r"error\s+handling", r"back-?off")),
    RubricItem("architecture", "Architecture", "engineering_depth", "architecture", 0.5,
               _rx(r"microservices?", r"system\s+design", r"architect(?:ed|ure)", r"multi[\s-]tenant", r"modular")),
]
RUBRIC_BY_ID = {r.id: r for r in RUBRIC}

# Display names for matched skills (what recruiters scan for).
SKILL_NAMES: dict[str, re.Pattern[str]] = {
    "Python": PYTHON, "FastAPI": _rx(r"fast\s?api"), "Django": _rx(r"\bdjango\b"), "Flask": _rx(r"\bflask\b"),
    "PostgreSQL": _rx(r"postgre(?:s|sql)\b"), "Redis": _rx(r"\bredis\b"), "MongoDB": _rx(r"mongo\s?db"),
    "MySQL": _rx(r"\bmysql\b"), "LangChain": _rx(r"lang\s?chain"), "LangGraph": _rx(r"lang\s?graph"),
    "LlamaIndex": _rx(r"llama\s?-?index"), "CrewAI": _rx(r"crew\s?ai"), "Google ADK": _rx(r"google\s+adk"),
    "MCP": _rx(r"\bmcp\b"), "RAG": _rx(r"\brag\b", r"retrieval[\s-]augmented"), "Embeddings": _rx(r"embeddings?"),
    "Vector DB": _rx(r"faiss", r"chroma", r"pinecone", r"qdrant", r"weaviate", r"milvus", r"pgvector", r"vector\s+(?:db|database|store)"),
    "OpenAI API": _rx(r"\bopenai\b"), "Gemini": _rx(r"\bgemini\b"), "Hugging Face": _rx(r"hugging\s?face"),
    "PyTorch": _rx(r"pytorch"), "TensorFlow": _rx(r"tensorflow"), "scikit-learn": _rx(r"scikit|sklearn"),
    "Docker": _rx(r"\bdocker"), "Kubernetes": _rx(r"kubernetes|\bk8s\b"), "GCP": _rx(r"\bgcp\b|google\s+cloud"),
    "AWS": _rx(r"\baws\b"), "Azure": _rx(r"\bazure\b"), "React": _rx(r"\breact(?:\.?js)?\b"), "Next.js": _rx(r"next\.?js"),
    "Node.js": _rx(r"node\.?js"), "TypeScript": _rx(r"typescript"), "JavaScript": _rx(r"javascript"),
    "Java": _rx(r"\bjava\b(?!\s*script)"), "Spring Boot": _rx(r"spring\s?boot"), "Kafka": _rx(r"\bkafka\b"),
    "Celery": _rx(r"\bcelery\b"), "pytest": _rx(r"\bpytest\b"), "CI/CD": _rx(r"ci\s?/\s?cd|github\s+actions"),
}
