"""Cheap deterministic signals. They run before the model and never need a network call."""

from __future__ import annotations

import re

DOC_EXT = (".md", ".markdown", ".rst", ".txt", ".adoc")
DOC_NAMES = ("readme", "license", "contributors", "authors", "changelog", "code_of_conduct")
LINKED_ISSUE = re.compile(r"\b(fix(es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s*#(\d+)", re.I)
ANY_ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")


def is_doc(path: str) -> bool:
    p = path.lower()
    name = p.rsplit("/", 1)[-1]
    return p.endswith(DOC_EXT) or any(name.startswith(n) for n in DOC_NAMES)


def changed_lines(patch: str) -> tuple[list[str], list[str]]:
    added, removed = [], []
    for line in (patch or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    return added, removed


def linked_issue(text: str) -> int | None:
    m = LINKED_ISSUE.search(text or "")
    if m:
        return int(m.group(3))
    m = ANY_ISSUE.search(text or "")
    return int(m.group(1)) if m else None


def signals(title: str, body: str, files: list[dict], author_association: str = "NONE") -> dict:
    """Return named signals plus a 0-100 'noise' score (higher = more likely low value)."""
    total_add = sum(f.get("additions", 0) for f in files)
    total_del = sum(f.get("deletions", 0) for f in files)
    paths = [f.get("filename", "") for f in files]
    docs_only = bool(paths) and all(is_doc(p) for p in paths)

    ws_only = True
    for f in files:
        a, r = changed_lines(f.get("patch", ""))
        if "".join("".join(x.split()) for x in a) != "".join("".join(x.split()) for x in r):
            ws_only = False
            break
    ws_only = ws_only and bool(files)

    s = {
        "files_changed": len(files),
        "lines_added": total_add,
        "lines_removed": total_del,
        "docs_only": docs_only,
        "whitespace_only": ws_only,
        "tiny_change": (total_add + total_del) <= 3,
        "linked_issue": linked_issue(f"{title}\n{body}"),
        "empty_description": len((body or "").strip()) < 20,
        "touches_ci_or_workflows": any(p.startswith(".github/workflows") for p in paths),
        "touches_dependencies": any(p.rsplit("/", 1)[-1] in (
            "package.json", "package-lock.json", "requirements.txt", "pyproject.toml",
            "go.mod", "Cargo.toml", "Gemfile", "pom.xml") for p in paths),
        "very_large": (total_add + total_del) > 1500,
        "first_time_contributor": author_association in ("FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE"),
    }

    noise = 0
    noise += 30 if s["docs_only"] and s["tiny_change"] else 0
    noise += 35 if s["whitespace_only"] else 0
    noise += 15 if s["linked_issue"] is None else 0
    noise += 10 if s["empty_description"] else 0
    noise += 10 if s["very_large"] and s["first_time_contributor"] else 0
    s["noise_score"] = min(noise, 100)

    risk = []
    if s["touches_ci_or_workflows"]:
        risk.append("changes CI workflows (can affect secrets and runners)")
    if s["touches_dependencies"]:
        risk.append("changes dependencies (supply-chain risk)")
    s["risk_notes"] = risk
    return s
