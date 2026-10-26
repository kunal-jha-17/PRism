"""Model-agnostic client for any OpenAI-compatible chat endpoint.

PRism is a harness, not a wrapper around one vendor. Pick a provider with
PRISM_PROVIDER, or point PRISM_BASE_URL at any compatible server.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

PROVIDERS = {
    # DigitalOcean serverless inference (Gradient AI / Inference Hub).
    "digitalocean": {
        "base_url": "https://inference.do-ai.run/v1",
        "key_env": "DO_MODEL_KEY",
        "default_model": "gemma-4-26b-a4b-it",
    },
    # Gemma 4 served through the Gemini API's OpenAI-compatible endpoint.
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "default_model": "gemma-4-26b-a4b-it",
    },
    # Fully local and free: `ollama pull gemma4` on a laptop or a GPU Droplet.
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_env": "",
        "default_model": "gemma4",
    },
}


class LLMError(RuntimeError):
    pass


def _detect_provider() -> str:
    """Use whichever key is configured, so setup is just 'add one secret'."""
    if os.getenv("PRISM_BASE_URL"):
        return "custom"
    if os.getenv("DO_MODEL_KEY"):
        return "digitalocean"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "ollama"


class LLM:
    """Minimal chat client. `complete_json` always returns a dict or raises."""

    def __init__(self, provider: str | None = None, model: str | None = None,
                 base_url: str | None = None, api_key: str | None = None,
                 vision: bool | None = None, timeout: int = 120):
        provider = (provider or os.getenv("PRISM_PROVIDER") or _detect_provider()).lower()
        cfg = PROVIDERS.get(provider, {"base_url": "", "key_env": "PRISM_API_KEY",
                                       "default_model": ""})
        self.provider = provider
        self.base_url = (base_url or os.getenv("PRISM_BASE_URL") or cfg["base_url"]).rstrip("/")
        self.model = model or os.getenv("PRISM_MODEL") or cfg["default_model"]
        key_env = cfg["key_env"]
        self.api_key = api_key or os.getenv("PRISM_API_KEY") or (os.getenv(key_env) if key_env else "") or ""
        if vision is None:
            vision = os.getenv("PRISM_VISION", "true").lower() != "false"
        self.vision = vision
        self.timeout = timeout
        if not self.base_url or not self.model:
            raise LLMError(f"Provider '{provider}' needs PRISM_BASE_URL and PRISM_MODEL.")

    @property
    def label(self) -> str:
        return f"{self.model} via {self.provider}"

    # ------------------------------------------------------------------ HTTP
    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(self.base_url + path, data=json.dumps(payload).encode(),
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:500]
                last = LLMError(f"HTTP {e.code} from {self.provider}: {body}")
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last
            except urllib.error.URLError as e:
                last = LLMError(f"Could not reach {self.base_url}: {e.reason}")
                time.sleep(2 * (attempt + 1))
        raise last or LLMError("request failed")

    def list_models(self) -> list[str]:
        req = urllib.request.Request(self.base_url + "/models")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode())
        return [m.get("id", "") for m in data.get("data", [])]

    def chat(self, system: str, user: str, images: list[str] | None = None,
             temperature: float = 0.1, max_tokens: int = 2000) -> str:
        if images and self.vision:
            content = [{"type": "text", "text": user}]
            content += [{"type": "image_url", "image_url": {"url": u}} for u in images[:4]]
        else:
            content = user
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": content}],
        }
        data = self._post("/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Unexpected response shape: {str(data)[:300]}")

    def complete_json(self, system: str, user: str, images: list[str] | None = None) -> dict:
        try:
            text = self.chat(system, user, images)
        except LLMError:
            if not images:
                raise
            text = self.chat(system, user, None)  # model or URL may not support images
        try:
            return parse_json(text)
        except ValueError:
            text = self.chat(system, user + "\n\nYour last reply was not valid JSON. "
                             "Reply with ONLY one JSON object, no prose, no code fences.")
            return parse_json(text)


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates code fences and prose)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                obj = json.loads(text[start:i + 1])
                if not isinstance(obj, dict):
                    raise ValueError("JSON is not an object")
                return obj
    raise ValueError("unterminated JSON object")
