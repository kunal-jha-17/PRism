# MLH submission answers (for DevRelay or the web form)

Event: Hacktoberfest Hack Day Delhi x SKILLOP DTU (`hacktoberfest-hack-day-delhi-x-skillop-dtu`)
Deadline: Oct 26, 4:00 PM IST. Team: Cryptix.

**Name:** PRism

**Short description (one-line pitch):**
An open-source review shield that runs on Gemma 4 and makes pull requests trustworthy again: it checks every claim in a PR, quizzes contributors on their own diff, and catches attempts to manipulate AI reviewers.

**Description:**
Hacktoberfest stopped counting pull requests in 2026 because low-effort and AI-generated PRs were burning out maintainers. PRism keeps the door open for real contributors instead of closing it. On every PR it posts claim receipts (each claim in the description checked against the diff), asks the contributor two questions about their own change and grades the answer, and labels and ranks the PR so maintainers review the best ones first. It detects hidden or manipulative text aimed at AI reviewers, learns from maintainer corrections stored in the repo, and never closes or merges anything on its own. It ships as a GitHub Action, a contributor preflight CLI and two agent skills, and runs on any OpenAI-compatible endpoint: Gemma 4 through the Gemini API, DigitalOcean Inference, or fully self-hosted with Ollama.

**Technologies:** Python, GitHub Actions, GitHub REST API, Gemma 4, Gemini API, Ollama (supported), Agent Skills (SKILL.md)

**AI the project calls:** Gemma 4 (`gemma-4-26b-a4b-it`)

**Source code:** https://github.com/kunal-jha-17/PRism

**Live demo / video:** _add the demo video link here_

**Extra links:** Demo pull requests: https://github.com/kunal-jha-17/PRism/pulls?q=is%3Apr

**AI coding tools:** Claude Code, model Claude Opus 5.5 (`coding:anthropic/claude-opus-5.5`)

## Prize categories

**Best Use of Gemma 4.** Gemma 4 is PRism's judgment engine: it reads the diff, linked issue and contribution guidelines, returns schema-validated JSON claim receipts, writes and grades diff-specific quiz questions, and uses Gemma 4's image input to check PR screenshots against the claimed change.

**Best Open-Source AI Project (DigitalOcean).** PRism is an MIT-licensed harness in which an open-weight model makes every triage decision. It ships as a GitHub Action, two agent skills and a CLI, runs on any OpenAI-compatible endpoint including DigitalOcean Inference or a self-hosted Ollama on a GPU Droplet, and targets the AI-slop problem that led Hacktoberfest to stop counting pull requests.
