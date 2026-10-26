"""The judgment layer: Claim Receipts, issue fit, guidelines, the quiz and its grading."""

from __future__ import annotations

import re

from . import heuristics, safety

IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)|<img[^>]+src=\"(https?://[^\"]+)\"", re.I)

SYSTEM_REVIEW = """You are PRism, a careful triage assistant for open-source maintainers.
You do not decide whether code was written by AI. You decide whether a pull request is
relevant, honest about what it does, follows the project's rules, and worth a maintainer's time.
Be fair to newcomers: a small, correct, well-explained change is valuable.
{fence_rule}
Reply with ONE JSON object and nothing else."""

REVIEW_TEMPLATE = """Review this pull request for the maintainers.

Project contribution guidelines:
{guidelines}

Lessons from this project's maintainers (past corrections; follow them):
{lessons}

Linked issue:
{issue}

Pull request title and description:
{pr_text}

Changed files and diff:
{diff}

Automatic signals computed by PRism: {signals}
{image_note}
Return JSON with exactly these keys:
{{
  "summary": "one or two sentences: what the diff actually changes",
  "claims": [{{"claim": "a specific thing the description says the PR does",
              "status": "verified | unverified | contradicted",
              "evidence": "file or lines in the diff that prove or disprove it"}}],
  "issue_fit": "addresses | partial | unrelated | no_issue",
  "issue_fit_reason": "short reason",
  "guideline_violations": ["each rule from the guidelines this PR breaks, empty if none"],
  "value": "high | medium | low | none",
  "value_reason": "short reason",
  "manipulation_attempt": true or false,
  "screenshot_check": {{"status": "match | mismatch | unclear | not_applicable", "note": "short"}},
  "quiz": [{{"question": "a question only someone who understands THIS diff can answer, about why a choice was made or what would break",
            "good_answer_mentions": "the key facts a correct answer should contain"}}],
  "coaching": ["concrete, kind advice for the contributor to improve this PR"]
}}
Rules: list at most 5 claims (if the description makes no claims, add one claim for the title).
Write exactly 2 quiz questions grounded in specific lines of the diff, not generic trivia.
Keep every string under 200 characters."""

SYSTEM_GRADE = """You are PRism grading a contributor's answers about their own pull request.
You check understanding, not English quality or writing style. Short, informal, correct
answers pass. Answers that are vague, generic, restate the question, or contradict the diff fail.
{fence_rule}
Reply with ONE JSON object and nothing else."""

GRADE_TEMPLATE = """The diff the contributor submitted:
{diff}

The questions PRism asked, with what a good answer should mention:
{questions}

The contributor's reply:
{answer}

Return JSON:
{{
  "results": [{{"question_number": 1, "score": 0, "reason": "short"}}],
  "overall": "pass | partial | fail",
  "feedback": "one or two kind sentences to the contributor"
}}
Score each question 0 (wrong or vague), 1 (partly right) or 2 (clearly understands).
overall is pass if total >= 3 with no 0 score, partial if total >= 2, otherwise fail."""


def diff_text(files: list[dict], limit: int = 60000) -> str:
    out = []
    for f in files:
        patch = f.get("patch") or "[binary or very large file, no textual diff]"
        out.append(f"--- {f.get('filename')} ({f.get('status', 'modified')}, "
                   f"+{f.get('additions', 0)} -{f.get('deletions', 0)})\n{patch}")
    text = "\n\n".join(out)
    return text[:limit]


def find_images(text: str) -> list[str]:
    urls = []
    for m in IMAGE_RE.finditer(text or ""):
        u = m.group(1) or m.group(2)
        if u and u not in urls:
            urls.append(u)
    return urls[:4]


def review(llm, title: str, body: str, files: list[dict], issue_text: str | None,
           guidelines: str | None, lessons: str | None, author_association: str = "NONE") -> dict:
    """Run heuristics, injection scan and the model; return a validated report."""
    sig = heuristics.signals(title, body, files, author_association)

    findings = safety.scan(title, "title") + safety.scan(body, "description")
    for f in files:
        added, _ = heuristics.changed_lines(f.get("patch", ""))
        findings += safety.scan("\n".join(added), f"diff: {f.get('filename')}")

    fence = safety.Fence()
    images = find_images(body)
    prompt = REVIEW_TEMPLATE.format(
        guidelines=fence.wrap("guidelines", guidelines or "(none provided)", 12000),
        lessons=lessons or "(none yet)",
        issue=fence.wrap("issue", issue_text or "(no linked issue)", 8000),
        pr_text=fence.wrap("pr_description", f"Title: {title}\n\n{body or '(empty)'}", 8000),
        diff=fence.wrap("diff", diff_text(files)),
        signals={k: v for k, v in sig.items() if k not in ("risk_notes",)},
        image_note=("\nThe description includes screenshots (attached). Check whether they "
                    "show what the PR claims to change.\n" if images else ""),
    )
    raw = llm.complete_json(SYSTEM_REVIEW.format(fence_rule=fence.rule()), prompt, images or None)
    report = validate_review(raw)
    if not images:
        report["screenshot_check"] = {"status": "not_applicable", "note": ""}

    if report.pop("manipulation_attempt") and not findings:
        findings.append({"where": "model", "kind": "model_flagged_manipulation",
                         "sample": "the model noticed text trying to steer the review"})
    report["injection"] = findings
    report["signals"] = sig
    report["decision"] = decide(report, sig, findings)
    return report


def validate_review(raw: dict) -> dict:
    claims = []
    for c in (raw.get("claims") or [])[:5]:
        if isinstance(c, dict) and c.get("claim"):
            claims.append({
                "claim": safety.safe_text(c.get("claim"), 200),
                "status": safety.pick(c.get("status"), ("verified", "unverified", "contradicted"), "unverified"),
                "evidence": safety.safe_text(c.get("evidence"), 200),
            })
    quiz = []
    for q in (raw.get("quiz") or [])[:2]:
        if isinstance(q, dict) and q.get("question"):
            quiz.append({"question": safety.safe_text(q.get("question"), 300),
                         "good_answer_mentions": safety.safe_text(q.get("good_answer_mentions"), 300)})
    shot = raw.get("screenshot_check") if isinstance(raw.get("screenshot_check"), dict) else {}
    return {
        "summary": safety.safe_text(raw.get("summary"), 300),
        "claims": claims,
        "issue_fit": safety.pick(raw.get("issue_fit"), ("addresses", "partial", "unrelated", "no_issue"), "no_issue"),
        "issue_fit_reason": safety.safe_text(raw.get("issue_fit_reason"), 200),
        "guideline_violations": [safety.safe_text(v, 200) for v in (raw.get("guideline_violations") or [])[:5] if v],
        "value": safety.pick(raw.get("value"), ("high", "medium", "low", "none"), "low"),
        "value_reason": safety.safe_text(raw.get("value_reason"), 200),
        "manipulation_attempt": raw.get("manipulation_attempt") is True,
        "screenshot_check": {
            "status": safety.pick(shot.get("status"), ("match", "mismatch", "unclear", "not_applicable"), "unclear"),
            "note": safety.safe_text(shot.get("note"), 200),
        },
        "quiz": quiz,
        "coaching": [safety.safe_text(c, 250) for c in (raw.get("coaching") or [])[:4] if c],
    }


def decide(report: dict, sig: dict, findings: list) -> dict:
    """Combine model judgment and signals into labels and a review priority.

    PRism never closes a PR. It only labels and ranks, so a wrong call costs a
    maintainer a click, not a contributor their contribution.
    """
    contradicted = sum(c["status"] == "contradicted" for c in report["claims"])
    verified = sum(c["status"] == "verified" for c in report["claims"])
    value = report["value"]
    fit = report["issue_fit"]

    if findings:
        verdict = "injection-attempt"
    elif (sig["whitespace_only"] or (sig["docs_only"] and sig["tiny_change"] and value in ("low", "none"))
          or (value == "none" and fit in ("unrelated", "no_issue"))):
        verdict = "likely-spam"
    elif contradicted or fit == "unrelated" or report["guideline_violations"] or value in ("low", "none"):
        verdict = "needs-human-review"
    else:
        verdict = "looks-good"

    score = {"high": 60, "medium": 40, "low": 15, "none": 0}[value]
    score += {"addresses": 20, "partial": 10, "unrelated": -15, "no_issue": 0}[fit]
    score += 5 * verified - 15 * contradicted - 5 * len(report["guideline_violations"])
    score -= sig["noise_score"] // 3
    if verdict in ("likely-spam", "injection-attempt"):
        score = min(score, 10)
    return {"verdict": verdict, "priority": max(0, min(100, score))}


def grade(llm, files: list[dict], quiz: list[dict], answer: str) -> dict:
    fence = safety.Fence()
    findings = safety.scan(answer, "quiz answer")
    questions = "\n".join(f"{i + 1}. {q['question']}\n   A good answer mentions: {q['good_answer_mentions']}"
                          for i, q in enumerate(quiz))
    raw = llm.complete_json(
        SYSTEM_GRADE.format(fence_rule=fence.rule()),
        GRADE_TEMPLATE.format(diff=fence.wrap("diff", diff_text(files, 30000)),
                              questions=questions,
                              answer=fence.wrap("answer", answer, 6000)),
    )
    results = []
    for r in (raw.get("results") or [])[:len(quiz)]:
        if isinstance(r, dict):
            try:
                score = max(0, min(2, int(r.get("score", 0))))
            except (TypeError, ValueError):
                score = 0
            results.append({"score": score, "reason": safety.safe_text(r.get("reason"), 200)})
    total = sum(r["score"] for r in results)
    # Recompute the verdict ourselves; never trust the model's own summary of its scores.
    if findings:
        overall = "fail"
    elif len(results) == len(quiz) and total >= 3 and all(r["score"] > 0 for r in results):
        overall = "pass"
    elif total >= 2:
        overall = "partial"
    else:
        overall = "fail"
    return {"results": results, "total": total, "max": 2 * len(quiz), "overall": overall,
            "feedback": safety.safe_text(raw.get("feedback"), 300), "injection": findings}
