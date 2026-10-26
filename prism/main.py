"""GitHub Action entry point.

Events:
  pull_request_target (opened / synchronize / reopened / edited) -> review
  issue_comment on a PR by its author while a quiz is pending    -> grade
  issue_comment `/prism right|wrong|vouch` by a maintainer         -> learn
  workflow_dispatch / schedule                                     -> review-queue digest

Security model: PRism never checks out or runs PR code. It reads the diff
through the API, gives the model no tools and no secrets, and only applies
labels from a fixed list.
"""

from __future__ import annotations

import json
import os
import sys

from . import analyze, heuristics, memory, render
from .github_api import GitHub
from .llm import LLM, LLMError

MAINTAINER_ASSOC = ("OWNER", "MEMBER", "COLLABORATOR")
GUIDELINE_FILES = ["CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md", "AGENTS.md"]
BOT_LOGIN = os.getenv("PRISM_BOT_LOGIN", "github-actions[bot]")
DIGEST_TITLE = "🔷 PRism review queue"


def log(*a):
    print("[prism]", *a, flush=True)


def ensure_labels(gh: GitHub):
    for name, (color, desc) in render.LABELS.items():
        gh.ensure_label(name, color, desc)


def find_state_comment(gh: GitHub, n: int) -> tuple[dict | None, dict | None]:
    """Only comments written by the bot account can carry state; anyone else's marker is ignored."""
    for c in reversed(gh.comments(n)):
        user = c.get("user") or {}
        if user.get("type") == "Bot" and user.get("login") == BOT_LOGIN:
            state = render.decode_state(c.get("body", ""))
            if state and state.get("kind") == "review":
                return c, state
    return None, None


def set_verdict_labels(gh: GitHub, n: int, current: list[str], wanted: list[str]):
    for name in current:
        if name in render.LABELS and name not in wanted:
            gh.remove_label(n, name)
    gh.add_labels(n, [w for w in wanted if w not in current])


# ---------------------------------------------------------------- review
def handle_review(gh: GitHub, llm: LLM, n: int):
    pr = gh.pr(n)
    if not pr or pr.get("state") != "open":
        return log("PR not open; nothing to do")
    author = pr["user"]["login"]
    if pr["user"].get("type") == "Bot":
        return log("PR opened by a bot; skipping")
    base_ref = pr["base"]["ref"]
    files = gh.pr_files(n)
    title, body = pr.get("title") or "", pr.get("body") or ""

    issue_text = None
    num = heuristics.linked_issue(f"{title}\n{body}")
    if num and num != n:
        iss = gh.issue(num)
        if iss and "pull_request" not in iss:
            issue_text = f"#{num}: {iss.get('title')}\n\n{iss.get('body') or ''}"

    # Read guidelines, lessons and trust list from the BASE branch, never from the PR.
    guidelines = gh.first_file(GUIDELINE_FILES, base_ref)
    lessons = memory.recent_lessons(gh.file(memory.LESSONS_PATH, base_ref)[0])
    trusted = memory.parse_trusted(gh.file(memory.TRUSTED_PATH, base_ref)[0])

    report = analyze.review(llm, title, body, files, issue_text, guidelines, lessons,
                            pr.get("author_association", "NONE"))

    old, old_state = find_state_comment(gh, n)
    already_passed = bool(old_state and old_state.get("quiz_status") == "pass")

    trusted_reason = ""
    quiz_everyone = os.getenv("PRISM_QUIZ_EVERYONE", "").lower() == "true"  # handy for demos
    if quiz_everyone and not already_passed:
        pass
    elif pr.get("author_association") in MAINTAINER_ASSOC:
        trusted_reason = "the author is a maintainer of this project"
    elif author.lower() in trusted:
        trusted_reason = "the author is on this project's trusted list"
    elif already_passed:
        trusted_reason = "the author already showed they understand this PR"
    quiz_required = not trusted_reason and bool(report["quiz"])

    comment_body = render.review_comment(report, author, llm.label, quiz_required, trusted_reason)
    state = {"kind": "review", "pr": n, "head": pr["head"]["sha"], "author": author,
             "verdict": report["decision"]["verdict"], "priority": report["decision"]["priority"],
             "summary": report["summary"][:200], "quiz": report["quiz"] if quiz_required else [],
             "attempts": 0,
             "quiz_status": "pass" if already_passed else ("pending" if quiz_required else "none")}
    comment_body += "\n" + render.encode_state(state)
    if old:
        gh.edit_comment(old["id"], comment_body)
    else:
        gh.comment(n, comment_body)

    ensure_labels(gh)
    wanted = [render.VERDICT_LABEL[state["verdict"]]]
    if state["quiz_status"] == "pending":
        wanted.append("prism:quiz-pending")
    if state["quiz_status"] == "pass":
        wanted.append("prism:verified-understanding")
    current = [lb["name"] for lb in pr.get("labels", [])]
    set_verdict_labels(gh, n, current, wanted)
    log(f"PR #{n}: {state['verdict']} priority={state['priority']} quiz={state['quiz_status']}")


# ---------------------------------------------------------------- comments
def handle_comment(gh: GitHub, llm: LLM, event: dict):
    issue, comment = event["issue"], event["comment"]
    if "pull_request" not in issue:
        return
    user = comment.get("user") or {}
    if user.get("type") == "Bot":
        return
    n, body, login = issue["number"], (comment.get("body") or "").strip(), user.get("login", "")
    assoc = comment.get("author_association", "NONE")

    if body.lower().startswith("/prism") and assoc in MAINTAINER_ASSOC:
        return handle_command(gh, n, body, login, issue)

    bot_comment, state = find_state_comment(gh, n)
    if not state or state.get("quiz_status") != "pending" or login != state.get("author"):
        return
    handle_answer(gh, llm, n, body, bot_comment, state, issue)


def handle_answer(gh, llm, n, answer, bot_comment, state, issue):
    files = gh.pr_files(n)
    result = analyze.grade(llm, files, state["quiz"], answer)
    state["attempts"] = state.get("attempts", 0) + 1
    attempts_left = max(0, 2 - state["attempts"])
    if result["overall"] == "pass":
        state["quiz_status"] = "pass"
    elif attempts_left == 0:
        state["quiz_status"] = "fail"
    gh.comment(n, render.grade_comment(result, state["author"], attempts_left))

    old_body = render.STATE_RE.sub(render.encode_state(state), bot_comment["body"])
    gh.edit_comment(bot_comment["id"], old_body)

    current = [lb["name"] for lb in issue.get("labels", [])]
    ensure_labels(gh)
    wanted = [render.VERDICT_LABEL[state["verdict"]]]
    if state["quiz_status"] == "pass":
        wanted.append("prism:verified-understanding")
    elif state["quiz_status"] == "pending":
        wanted.append("prism:quiz-pending")
    else:
        wanted.append("prism:needs-human-review")
    set_verdict_labels(gh, n, current, list(dict.fromkeys(wanted)))
    log(f"PR #{n}: quiz {result['overall']} ({result['total']}/{result['max']})")


def handle_command(gh: GitHub, n: int, body: str, maintainer: str, issue: dict):
    parts = body.split(None, 2)
    cmd = parts[1].lower() if len(parts) > 1 else "help"
    reason = parts[2] if len(parts) > 2 else ""
    repo = gh._req("GET", f"/repos/{gh.repo}")
    branch = repo["default_branch"]
    _, state = find_state_comment(gh, n)

    if cmd in ("right", "wrong"):
        if not state:
            return gh.comment(n, "PRism has no review on this PR yet, so there is nothing to learn from.")
        text, sha = gh.file(memory.LESSONS_PATH, branch)
        entry = memory.lesson_entry(n, issue.get("title", ""), state["verdict"], cmd == "right", reason, maintainer)
        gh.put_file(memory.LESSONS_PATH, (text or memory.LESSONS_HEADER) + entry,
                    f"PRism: learn from PR #{n} ({cmd})", branch, sha)
        msg = ("👍 Noted, PRism will keep doing this." if cmd == "right" else
               "📝 Thanks. Lesson saved to `.prism/lessons.md`; PRism reads it before every future review.")
        return gh.comment(n, msg)

    if cmd == "vouch":
        author = (state or {}).get("author") or issue["user"]["login"]
        text, sha = gh.file(memory.TRUSTED_PATH, branch)
        gh.put_file(memory.TRUSTED_PATH, memory.add_trusted(text, author, f"vouched by {maintainer} on #{n}"),
                    f"PRism: trust {author}", branch, sha)
        return gh.comment(n, f"🤝 `@{author}` added to `.prism/trusted.txt`. Future PRs skip the quiz.")

    gh.comment(n, "PRism commands for maintainers: `/prism right`, `/prism wrong <reason>`, `/prism vouch`.")


# ---------------------------------------------------------------- digest
def handle_digest(gh: GitHub):
    rows = []
    for pr in gh.open_prs():
        _, state = find_state_comment(gh, pr["number"])
        if state:
            rows.append((state.get("priority", 0), pr, state))
    rows.sort(key=lambda r: -r[0])
    icon = {"looks-good": "🟢", "needs-human-review": "🟡", "likely-spam": "🔴", "injection-attempt": "🟣"}
    quiz = {"pass": "✅ verified", "pending": "⏳ waiting", "fail": "❌ failed", "none": "—"}
    lines = ["Open PRs ranked by PRism. Review from the top; the bottom can wait.", "",
             "| Priority | PR | Verdict | Understanding | Summary |", "|---|---|---|---|---|"]
    for prio, pr, st in rows:
        lines.append(f"| **{prio}** | #{pr['number']} | {icon.get(st['verdict'], '')} {st['verdict']} | "
                     f"{quiz.get(st.get('quiz_status', 'none'), '—')} | {st.get('summary', '')} |")
    if not rows:
        lines.append("| | | | | No reviewed PRs yet |")
    body = "\n".join(lines)
    existing = gh.find_issue(DIGEST_TITLE)
    if existing:
        gh.edit_issue(existing["number"], body)
    else:
        gh.create_issue(DIGEST_TITLE, body)
    log(f"digest updated with {len(rows)} PR(s)")


def main():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    with open(os.environ["GITHUB_EVENT_PATH"]) as fh:
        event = json.load(fh)
    gh = GitHub(os.environ["GITHUB_REPOSITORY"])

    if event_name in ("workflow_dispatch", "schedule"):
        return handle_digest(gh)
    llm = LLM()
    log(f"model: {llm.label}")
    try:
        if event_name in ("pull_request", "pull_request_target"):
            if event.get("action") in ("opened", "synchronize", "reopened", "edited", "ready_for_review"):
                handle_review(gh, llm, event["pull_request"]["number"])
        elif event_name == "issue_comment" and event.get("action") == "created":
            handle_comment(gh, llm, event)
        else:
            log(f"ignoring event {event_name}")
    except LLMError as exc:
        hint = ""
        try:
            ids = [m for m in llm.list_models() if "gemma" in m.lower()]
            hint = f" Gemma models this key can use: {', '.join(ids) or 'none found'}. Set the PRISM_MODEL repo variable."
        except Exception:
            pass
        raise LLMError(f"{exc}{hint}") from None


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail loudly in the Actions log, never with a half-applied state
        print(f"::error::PRism failed: {exc}", file=sys.stderr)
        raise
