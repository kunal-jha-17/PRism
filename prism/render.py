"""Turn reports into GitHub comments. All model text was already passed through safety.safe_text."""

from __future__ import annotations

import base64
import json
import re

STATE_RE = re.compile(r"<!-- prism:state ([A-Za-z0-9+/=]+) -->")

LABELS = {
    "prism:looks-good": ("2da44e", "PRism: relevant, claims check out"),
    "prism:needs-human-review": ("d29922", "PRism: a maintainer should look closely"),
    "prism:likely-spam": ("cf222e", "PRism: low-value or spam-like change"),
    "prism:injection-attempt": ("8250df", "PRism: PR text tried to manipulate the reviewer"),
    "prism:quiz-pending": ("0969da", "PRism: waiting for the contributor's answers"),
    "prism:verified-understanding": ("1f883d", "PRism: contributor showed they understand the change"),
}
VERDICT_LABEL = {
    "looks-good": "prism:looks-good",
    "needs-human-review": "prism:needs-human-review",
    "likely-spam": "prism:likely-spam",
    "injection-attempt": "prism:injection-attempt",
}
BADGE = {
    "looks-good": "🟢 **Looks good**: relevant change, claims check out",
    "needs-human-review": "🟡 **Needs human review**",
    "likely-spam": "🔴 **Likely spam / low value**",
    "injection-attempt": "🟣 **Manipulation attempt detected**",
}
CLAIM_ICON = {"verified": "✅", "unverified": "❔", "contradicted": "❌"}
FIT = {"addresses": "✅ addresses the linked issue", "partial": "🟡 partly addresses the linked issue",
       "unrelated": "❌ does not match the linked issue", "no_issue": "➖ no linked issue"}


def encode_state(state: dict) -> str:
    return f"<!-- prism:state {base64.b64encode(json.dumps(state).encode()).decode()} -->"


def decode_state(body: str) -> dict | None:
    m = STATE_RE.search(body or "")
    if not m:
        return None
    try:
        return json.loads(base64.b64decode(m.group(1)))
    except (ValueError, json.JSONDecodeError):
        return None


def review_comment(report: dict, author: str, model_label: str, quiz_required: bool,
                   trusted_reason: str = "") -> str:
    d = report["decision"]
    lines = ["## 🔷 PRism review", "", f"{BADGE[d['verdict']]} · review priority **{d['priority']}/100**", ""]
    if report["summary"]:
        lines += [f"**What this PR actually changes:** {report['summary']}", ""]

    if report["injection"]:
        lines += ["> [!WARNING]",
                  "> This PR contains text aimed at an AI reviewer, or hidden from human readers. "
                  "PRism ignored it and is flagging it for maintainers:"]
        for f in report["injection"][:5]:
            lines.append(f"> - `{f['kind']}` in {f['where']}: {_quote(f['sample'])}")
        lines.append("")

    if report["claims"]:
        lines += ["### 🧾 Claim receipts", "", "| | Claim in the description | Evidence in the diff |", "|---|---|---|"]
        for c in report["claims"]:
            lines.append(f"| {CLAIM_ICON[c['status']]} | {c['claim']} | {c['evidence'] or '—'} |")
        lines.append("")

    lines.append(f"**Issue fit:** {FIT[report['issue_fit']]}"
                 + (f": {report['issue_fit_reason']}" if report["issue_fit_reason"] else ""))
    lines.append(f"**Value:** {report['value']}" + (f": {report['value_reason']}" if report["value_reason"] else ""))
    if report["guideline_violations"]:
        lines += ["", "**Contribution guideline issues:**"] + [f"- {v}" for v in report["guideline_violations"]]
    if report["signals"]["risk_notes"]:
        lines += ["", "**Risk notes:** " + "; ".join(report["signals"]["risk_notes"])]
    shot = report["screenshot_check"]
    if shot["status"] != "not_applicable":
        icon = {"match": "✅", "mismatch": "❌", "unclear": "❔"}[shot["status"]]
        lines += ["", f"**Screenshot check:** {icon} {shot['note']}"]
    lines.append("")

    if quiz_required and report["quiz"]:
        lines += [f"### 🧠 Earn your vouch, `@{author}`", "",
                  "To help maintainers review faster, please answer these in a reply, in your own words. "
                  "Short answers are fine; this checks understanding, not English. "
                  "Using AI tools to write code is okay. Understanding the change is what matters.", ""]
        for i, q in enumerate(report["quiz"], 1):
            lines.append(f"{i}. {q['question']}")
        lines.append("")
    elif trusted_reason:
        lines += [f"_No quiz needed: {trusted_reason}._", ""]

    if report["coaching"]:
        lines += ["<details><summary>💡 How to make this PR easier to merge</summary>", ""]
        lines += [f"- {c}" for c in report["coaching"]] + ["", "</details>", ""]

    lines += ["---",
              f"<sub>PRism never closes PRs; a maintainer always decides. Model: `{model_label}` (open-weight). "
              "Maintainers can reply `/prism right`, `/prism wrong <reason>` or `/prism vouch` "
              "to teach PRism.</sub>"]
    return "\n".join(lines)


def grade_comment(result: dict, author: str, attempts_left: int) -> str:
    head = {"pass": f"✅ **Understanding verified.** Thanks `@{author}`, this PR is marked `prism:verified-understanding`.",
            "partial": "🟡 **Partly there.**",
            "fail": "❌ **Not enough to verify understanding yet.**"}[result["overall"]]
    lines = ["## 🔷 PRism quiz result", "", head, "", f"Score: **{result['total']}/{result['max']}**", ""]
    for i, r in enumerate(result["results"], 1):
        lines.append(f"- Q{i}: {'●' * r['score']}{'○' * (2 - r['score'])} {r['reason']}")
    if result["feedback"]:
        lines += ["", result["feedback"]]
    if result["injection"]:
        lines += ["", "> [!WARNING]", "> The reply contained text aimed at an AI grader, so it was not accepted."]
    if result["overall"] != "pass":
        lines += ["", (f"You can reply once more with a clearer answer ({attempts_left} attempt left)."
                       if attempts_left > 0 else "A maintainer will review this PR manually.")]
    return "\n".join(lines)


def _quote(s: str) -> str:
    return "`" + s.replace("`", "'") + "`"
