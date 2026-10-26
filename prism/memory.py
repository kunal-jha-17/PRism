"""Maintainer-taught memory and the trusted-contributor list.

Both live as plain files in the repository, so every lesson and every vouch is
visible, reviewable and version-controlled. No model training is involved.
"""

from __future__ import annotations

import datetime as dt
import re

LESSONS_PATH = ".prism/lessons.md"
TRUSTED_PATH = ".prism/trusted.txt"
LESSONS_HEADER = ("# PRism lessons\n\nMaintainer corrections. PRism reads the most recent ones before every "
                  "review. Edit or delete freely.\n")


def recent_lessons(text: str | None, n: int = 8) -> str | None:
    if not text:
        return None
    entries = [e.strip() for e in re.split(r"\n(?=- \*\*)", text) if e.strip().startswith("- **")]
    return "\n".join(entries[-n:]) if entries else None


def lesson_entry(pr_number: int, title: str, verdict: str, correct: bool, reason: str, who: str) -> str:
    day = dt.date.today().isoformat()
    outcome = "PRism was right" if correct else "PRism was WRONG"
    reason = " ".join((reason or "").split())[:300] or "no reason given"
    title = " ".join(title.split())[:120]
    return f"- **{day} · PR #{pr_number} \"{title}\"**: PRism said `{verdict}`. {outcome}. Maintainer @{who}: {reason}\n"


def parse_trusted(text: str | None) -> set[str]:
    out = set()
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip().lstrip("@").lower()
        if line:
            out.add(line)
    return out


def add_trusted(text: str | None, login: str, reason: str) -> str:
    text = text or "# Contributors trusted by this project (one GitHub username per line).\n"
    if login.lower() in parse_trusted(text):
        return text
    return text.rstrip("\n") + f"\n{login}  # {reason}, {dt.date.today().isoformat()}\n"
