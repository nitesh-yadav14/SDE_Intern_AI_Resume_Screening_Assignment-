"""Find signals in a parsed resume and turn them into quoted evidence."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Block, Line, ParsedResume


@dataclass
class Hit:
    line: Line
    match: str

    def quote(self, width: int = 170) -> str:
        """Window of the line around the match, so long lines stay readable."""
        text = self.line.text
        if len(text) <= width:
            return text
        idx = text.lower().find(self.match.lower())
        start = max(0, idx - width // 3)
        snippet = text[start:start + width]
        return ("…" if start else "") + snippet + ("…" if start + width < len(text) else "")


def find(pattern: re.Pattern[str], lines: list[Line], sections: set[str] | None = None,
         mask: re.Pattern[str] | None = None) -> list[Hit]:
    """Lines matching ``pattern``; ``mask`` blanks phrases first (e.g. 'GitHub Copilot')."""
    hits = []
    for ln in lines:
        if sections is not None and ln.section not in sections:
            continue
        text = mask.sub(" ", ln.text) if mask else ln.text
        m = pattern.search(text)
        if m:
            hits.append(Hit(ln, m.group(0)))
    return hits


def block_lines(resume: ParsedResume, block: Block) -> list[Line]:
    wanted = set(block.lines)
    return [ln for ln in resume.lines if ln.no in wanted]


def best_hit(hits: list[Hit], context_weight: dict[str, float]) -> tuple[Hit | None, float]:
    """Hit in the most credible section (experience/projects beat skills lists)."""
    best, best_w = None, 0.0
    for h in hits:
        w = context_weight.get(h.line.section, 0.5)
        if w > best_w:
            best, best_w = h, w
    return best, best_w
