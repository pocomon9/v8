from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request


log = logging.getLogger("nexus.llm")


DEFAULT_ROLE_MODELS = {
    "chat": ["tinyllama", "phi3:mini", "deepseek-coder:1.3b"],
    "summary": ["tinyllama", "phi3:mini"],
    "debug": ["deepseek-coder:1.3b", "qwen2.5-coder:1.5b", "phi3:mini"],
    "quick": ["tinyllama", "phi3:mini"],
}

ROLE_ENV_MAP = {
    "chat": "poco_MODEL_CHAT",
    "summary": "poco_MODEL_SUMMARY",
    "debug": "poco_MODEL_DEBUG",
    "quick": "poco_MODEL_QUICK",
}


def _parse_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except Exception:
        return default


class LocalLLM:
    def __init__(self, model: str | None = None):
        self.host = os.environ.get("OLLAMA_HOST", "").strip().rstrip("/")
        self.local_ollama_binary = shutil.which("ollama") or ""
        fallback_models = _parse_models(
            os.environ.get(
                "poco_OLLAMA_MODELS",
                "deepseek-coder:1.3b,qwen2.5-coder:1.5b,phi3:mini,tinyllama",
            )
        )
        primary = (model or os.environ.get("poco_PRIMARY_MODEL", "deepseek-coder:1.3b")).strip()
        self.base_candidates = [primary, *[item for item in fallback_models if item != primary]]
        self.role_models: dict[str, list[str]] = {}
        for role, defaults in DEFAULT_ROLE_MODELS.items():
            configured = _parse_models(os.environ.get(ROLE_ENV_MAP[role], ""))
            pool = configured or list(defaults)
            ordered = [*pool, *self.base_candidates]
            seen = set()
            deduped: list[str] = []
            for candidate in ordered:
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    deduped.append(candidate)
            self.role_models[role] = deduped

    def candidates_for_role(self, role: str = "chat") -> list[str]:
        return list(self.role_models.get((role or "chat").strip().lower(), self.base_candidates))

    def _normalize_output(self, output: str) -> str:
        text = (output or "").strip()
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text.startswith("```"):
            text = text.strip("`").strip()
            if "\n" in text:
                text = text.split("\n", 1)[1].strip()
        for prefix in ("Here is the post:", "Here's the post:", "Post:", "Reply:", "JSON:"):
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
        return text

    def _ask_remote(self, prompt: str, candidate: str, timeout: int) -> str:
        payload = json.dumps({"model": candidate, "prompt": prompt, "stream": False}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", errors="ignore"))
        return str(body.get("response", "") or "").strip()

    def _ask_local(self, prompt: str, candidate: str, timeout: int) -> str:
        result = subprocess.run(
            [self.local_ollama_binary or "ollama", "run", candidate],
            capture_output=True,
            text=True,
            timeout=timeout,
            input=prompt,
        )
        return result.stdout.strip()

    def ask(self, prompt: str, timeout: int = 45, role: str = "chat") -> str:
        prompt = (prompt or "").strip()
        if not prompt:
            return ""
        candidates = self.candidates_for_role(role)
        log.info("LLM route role=%s candidates=%s", role, ",".join(candidates[:3]))
        local_timeout = max(5, _env_int("poco_LOCAL_LLM_TIMEOUT_SECONDS", timeout))
        remote_timeout = max(5, _env_int("poco_REMOTE_LLM_TIMEOUT_SECONDS", timeout))

        return ""
