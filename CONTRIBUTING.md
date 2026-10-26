# Contributing to PRism

Thanks for helping. PRism reviews its own pull requests, so these rules are also what the bot checks.

1. **Link an issue.** Every PR should say which issue it fixes, e.g. `Fixes #1`.
2. **Keep it focused.** One change per PR. Don't mix a bug fix with unrelated refactoring.
3. **Bug fixes need a test** that fails before your change and passes after it.
4. **No refactors nobody asked for.** Open an issue first to discuss larger restructuring.
5. **Describe honestly.** Only claim what the diff actually does.
6. **Using AI tools is fine.** You must understand your change well enough to explain it; PRism may ask you two short questions about it.
7. **No text aimed at bots.** Hidden comments or instructions for AI reviewers will be flagged.

Run the checks locally before opening a PR:

```bash
python3 -m unittest discover -s tests
python3 -m prism.cli preflight --base main   # optional: needs a model key or local Ollama
```
