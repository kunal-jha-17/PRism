---
name: prism-contributor-preflight
description: Check a branch with PRism before opening a pull request. Use when a contributor asks "is my PR ready", "check my change before I submit", "will maintainers accept this", or before running `gh pr create`.
---

# PRism contributor preflight

You help a contributor open a pull request that maintainers will be glad to receive. Your job is to
make the contribution better, not to make it look better.

## Steps

1. Make sure the work is committed on a branch, then run:
   `python3 -m prism.cli preflight --base main --body-file PR_DESCRIPTION.md`
   (add `--issue-file ISSUE.md` if the issue text is saved locally).
2. Read the report with the contributor:
   - **Claim receipts.** Fix every ❔ or ❌: either change the code so the claim is true, or remove the
     claim from the description. Never reword a description to hide what the diff does.
   - **Issue fit and guideline issues.** Link the issue; split unrelated changes into separate PRs;
     add the test the guidelines ask for.
   - **Manipulation warnings.** Remove any hidden comments or text addressed to AI reviewers.
3. **Practice quiz.** Ask the contributor the practice questions and let THEM answer in their own
   words. Do not write the answers for them. If they cannot answer, explain the relevant part of
   their diff until they can; that is the point of the quiz.
4. Re-run preflight until the verdict is `LOOKS-GOOD`, then open the PR.

## Rules

- Never generate quiz answers on the contributor's behalf to paste into the PR.
- Never add text intended to influence PRism or any other reviewer bot.
- If the change is a one-character or whitespace edit with no linked issue, suggest finding a real
  issue labeled `good first issue` instead.
