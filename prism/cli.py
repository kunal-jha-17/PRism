"""Command line for contributors and maintainers.

  python -m prism.cli preflight [--base main] [--title ...] [--body-file PR.md] [--issue-file ISSUE.md]
      Check your branch BEFORE opening a PR: same checks maintainers will see, plus a practice quiz.
  python -m prism.cli models
      List the models your configured provider offers (handy for finding the Gemma 4 id).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from . import analyze
from .llm import LLM


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def files_from_git(base: str) -> list[dict]:
    """Build the same file list the GitHub API returns, from the local branch."""
    merge_base = git("merge-base", base, "HEAD").strip()
    numstat = git("diff", "--numstat", merge_base, "HEAD").splitlines()
    files = []
    for row in numstat:
        add, dele, path = row.split("\t", 2)
        patch = git("diff", merge_base, "HEAD", "--", path)
        patch = "\n".join(patch.splitlines()[4:]) if patch else ""
        files.append({"filename": path, "status": "modified",
                      "additions": int(add) if add.isdigit() else 0,
                      "deletions": int(dele) if dele.isdigit() else 0,
                      "patch": patch})
    return files


def read(path: str | None) -> str | None:
    return Path(path).read_text() if path and Path(path).exists() else None


def print_report(report: dict, llm: LLM):
    d = report["decision"]
    print(f"\nPRism preflight  ·  model: {llm.label}\n" + "=" * 60)
    print(f"Maintainers would see: {d['verdict'].upper()}  (priority {d['priority']}/100)\n")
    print(f"What your diff actually changes: {report['summary']}\n")
    if report["injection"]:
        print("!! Text that looks aimed at an AI reviewer or hidden from humans (remove it):")
        for f in report["injection"]:
            print(f"   - {f['kind']} in {f['where']}: {f['sample']}")
        print()
    if report["claims"]:
        print("Claim receipts:")
        icon = {"verified": "[ok]", "unverified": "[??]", "contradicted": "[NO]"}
        for c in report["claims"]:
            print(f"  {icon[c['status']]} {c['claim']}\n        evidence: {c['evidence']}")
        print()
    print(f"Issue fit: {report['issue_fit']}  {report['issue_fit_reason']}")
    print(f"Value: {report['value']}  {report['value_reason']}")
    for v in report["guideline_violations"]:
        print(f"Guideline issue: {v}")
    if report["coaching"]:
        print("\nHow to improve before submitting:")
        for c in report["coaching"]:
            print(f"  - {c}")
    if report["quiz"]:
        print("\nPractice quiz (maintainers' PRism will ask questions like these):")
        for i, q in enumerate(report["quiz"], 1):
            print(f"  {i}. {q['question']}")
    print()


def main(argv=None):
    p = argparse.ArgumentParser(prog="prism")
    sub = p.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("preflight", help="check your branch before opening a PR")
    pf.add_argument("--base", default="main")
    pf.add_argument("--title", default=None)
    pf.add_argument("--body-file", default=None)
    pf.add_argument("--issue-file", default=None)
    pf.add_argument("--guidelines", default="CONTRIBUTING.md")
    sub.add_parser("models", help="list models available from the configured provider")
    args = p.parse_args(argv)

    llm = LLM()
    if args.cmd == "models":
        for m in llm.list_models():
            print(m)
        return 0

    files = files_from_git(args.base)
    if not files:
        print(f"No changes between {args.base} and HEAD.")
        return 1
    title = args.title or git("log", "-1", "--format=%s").strip()
    body = read(args.body_file) or git("log", f"{args.base}..HEAD", "--format=%B").strip()
    issue = read(args.issue_file)
    lessons_text = read(".prism/lessons.md")
    lessons = "\n".join(re.findall(r"^- \*\*.*$", lessons_text or "", re.M)[-8:]) or None
    report = analyze.review(llm, title, body, files, issue, read(args.guidelines), lessons, "NONE")
    print_report(report, llm)
    return 0 if report["decision"]["verdict"] == "looks-good" else 2


if __name__ == "__main__":
    sys.exit(main())
