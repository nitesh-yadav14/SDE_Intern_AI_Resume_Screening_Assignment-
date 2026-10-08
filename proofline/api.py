"""Optional HTTP wrapper (bonus):  uvicorn proofline.api:app --reload

POST /screen   {"input_dir": "./resumes", "github": true, "llm": false}  → runs a batch
GET  /results  → last batch result
GET  /results/{rank} → one ranked candidate with its evidence ledger
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import load_settings
from .pipeline import run

app = FastAPI(title="Proofline", version="1.0")
_last: dict | None = None


class ScreenRequest(BaseModel):
    input_dir: str = "./resumes"
    github: bool = True
    llm: bool = False


@app.post("/screen")
def screen(req: ScreenRequest) -> dict:
    global _last
    folder = Path(req.input_dir)
    if not folder.is_dir():
        raise HTTPException(400, f"input_dir not found: {folder}")
    _last = run(folder, load_settings(), use_github=req.github, use_llm=req.llm)
    return _last["batch_summary"]


@app.get("/results")
def results() -> dict:
    if _last is None:
        raise HTTPException(404, "no batch has been screened yet — POST /screen first")
    return _last


@app.get("/results/{rank}")
def result(rank: int) -> dict:
    if _last is None or not 1 <= rank <= len(_last["ranking"]):
        raise HTTPException(404, "no such rank")
    return _last["ranking"][rank - 1]
