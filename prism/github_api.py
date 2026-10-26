"""Tiny GitHub REST client (standard library only)."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class GitHub:
    def __init__(self, repo: str, token: str | None = None, api: str | None = None):
        self.repo = repo
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.api = (api or os.getenv("GITHUB_API_URL") or "https://api.github.com").rstrip("/")

    def _req(self, method: str, path: str, data=None, accept: str = "application/vnd.github+json"):
        url = path if path.startswith("http") else f"{self.api}{path}"
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Accept", accept)
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "prism-action")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw and accept.endswith("json") else raw
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise RuntimeError(f"GitHub {method} {path} -> {e.code}: {e.read().decode()[:300]}")

    def _paged(self, path: str, limit: int = 300) -> list:
        out, page = [], 1
        sep = "&" if "?" in path else "?"
        while len(out) < limit:
            batch = self._req("GET", f"{path}{sep}per_page=100&page={page}") or []
            out += batch
            if len(batch) < 100:
                break
            page += 1
        return out[:limit]

    # ---------------------------------------------------------------- reads
    def pr(self, n: int) -> dict:
        return self._req("GET", f"/repos/{self.repo}/pulls/{n}")

    def pr_files(self, n: int) -> list[dict]:
        return self._paged(f"/repos/{self.repo}/pulls/{n}/files")

    def issue(self, n: int) -> dict | None:
        return self._req("GET", f"/repos/{self.repo}/issues/{n}")

    def comments(self, n: int) -> list[dict]:
        return self._paged(f"/repos/{self.repo}/issues/{n}/comments")

    def open_prs(self) -> list[dict]:
        return self._paged(f"/repos/{self.repo}/pulls?state=open", 100)

    def file(self, path: str, ref: str | None = None) -> tuple[str | None, str | None]:
        q = f"?ref={urllib.parse.quote(ref)}" if ref else ""
        data = self._req("GET", f"/repos/{self.repo}/contents/{urllib.parse.quote(path)}{q}")
        if not data or isinstance(data, list) or "content" not in data:
            return None, None
        return base64.b64decode(data["content"]).decode(errors="replace"), data.get("sha")

    def first_file(self, paths: list[str], ref: str | None = None) -> str | None:
        for p in paths:
            text, _ = self.file(p, ref)
            if text:
                return text
        return None

    # --------------------------------------------------------------- writes
    def put_file(self, path: str, text: str, message: str, branch: str, sha: str | None):
        data = {"message": message, "content": base64.b64encode(text.encode()).decode(), "branch": branch}
        if sha:
            data["sha"] = sha
        return self._req("PUT", f"/repos/{self.repo}/contents/{urllib.parse.quote(path)}", data)

    def comment(self, n: int, body: str) -> dict:
        return self._req("POST", f"/repos/{self.repo}/issues/{n}/comments", {"body": body})

    def edit_comment(self, comment_id: int, body: str) -> dict:
        return self._req("PATCH", f"/repos/{self.repo}/issues/comments/{comment_id}", {"body": body})

    def add_labels(self, n: int, labels: list[str]):
        if labels:
            self._req("POST", f"/repos/{self.repo}/issues/{n}/labels", {"labels": labels})

    def remove_label(self, n: int, label: str):
        self._req("DELETE", f"/repos/{self.repo}/issues/{n}/labels/{urllib.parse.quote(label)}")

    def ensure_label(self, name: str, color: str, description: str):
        if self._req("GET", f"/repos/{self.repo}/labels/{urllib.parse.quote(name)}") is None:
            try:
                self._req("POST", f"/repos/{self.repo}/labels",
                          {"name": name, "color": color, "description": description})
            except RuntimeError:
                pass  # created concurrently

    def find_issue(self, title: str) -> dict | None:
        for i in self._paged(f"/repos/{self.repo}/issues?state=open", 200):
            if i.get("title") == title and "pull_request" not in i:
                return i
        return None

    def create_issue(self, title: str, body: str) -> dict:
        return self._req("POST", f"/repos/{self.repo}/issues", {"title": title, "body": body})

    def edit_issue(self, n: int, body: str) -> dict:
        return self._req("PATCH", f"/repos/{self.repo}/issues/{n}", {"body": body})
