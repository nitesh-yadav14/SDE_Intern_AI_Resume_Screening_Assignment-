"""Proofline CLI.

    python main.py --input ./resumes --output ./output/results.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from proofline.config import load_settings
from proofline.pipeline import run
from proofline.report import render_html, render_terminal


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evidence-ledger resume screening for AI/agentic SDE interns")
    p.add_argument("--input", default="./resumes", help="folder of .pdf/.docx/.txt resumes")
    p.add_argument("--output", default="./output/results.json", help="where to write results JSON")
    p.add_argument("--report", default=None, help="HTML report path (default: next to --output)")
    p.add_argument("--config", default=None, help="alternative proofline.toml")
    p.add_argument("--no-github", action="store_true", help="skip GitHub enrichment (offline run)")
    p.add_argument("--llm", action="store_true", help="enable the LLM second reviewer (needs LLM_API_KEY)")
    p.add_argument("--workers", type=int, default=4, help="parallel PDF parsing processes (1 = sequential)")
    p.add_argument("--top", type=int, default=15, help="rows to print in the terminal table")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"error: input folder not found: {input_dir}", file=sys.stderr)
        return 2
    settings = load_settings(args.config)
    result = run(input_dir, settings, use_github=not args.no_github, use_llm=args.llm, workers=args.workers)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    report = Path(args.report) if args.report else out.with_name("report.html")
    report.write_text(render_html(result), encoding="utf-8")

    print(render_terminal(result, top=args.top))
    print(f"\n  results → {out}\n  report  → {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
