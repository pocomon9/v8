from __future__ import annotations

import json
import hashlib
import logging
import os
import random
import re
import shutil
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
import urllib.parse
import urllib.request
import subprocess
import tempfile

import schedule

from .brain_planner import BrainPlanner
from .codex import _Mx as _Codex
from .concept_anchors import ConceptSelector
from .config import AccountsConfig
from .entropy_source import QuantumEntropy
from .github_ops import GitHubOps
from .llm_client import LocalLLM
from .memory_system import MemorySystem
from .prompt_templates import PromptTemplates
from .runtime_paths import PROJECT_ROOT
from .selenium_controller import SeleniumController
from .self_heal import SelfHealer
from .trend_hunter import MISSION_PHRASES, MISSION_TERMS, SHOPPING_PHRASES, SHOPPING_TERMS, TrendHunter
from .viral_intelligence import ViralIntelligence
from .modules.signal_hunter import SignalHunter
from .modules.memory_vault import MemoryVault
from .modules.reputation_guard import ReputationGuard
from .modules.influence_engine import InfluenceEngine
from .modules.risk_monitor import RiskMonitor


log = logging.getLogger("final-puss.engine")


PUBLIC_BOILERPLATE_PATTERNS = (
    r"\bi(?:'| a)?m\s+sorry\b",
    r"\bsorry[, ]",
    r"\bi\s+apologize\b",
    r"\bi\s+(?:can'?t|cannot|won'?t)\s+(?:assist|help|comply|provide|continue|answer)\b",
    r"\bi\s+am\s+unable\s+to\b",
    r"\bi(?:'| a)?m\s+unable\s+to\b",
    r"\bunable\s+to\s+(?:assist|help|comply|provide|continue|answer)\b",
    r"\bcan'?t\s+(?:assist|help|comply|provide)\s+with\s+that\b",
    r"\bcannot\s+(?:assist|help|comply|provide)\s+with\s+that\b",
    r"\bas\s+(?:an?\s+)?(?:ai|language model|assistant)\b",
    r"\b(?:ai|language model|virtual assistant|chatbot)\b",
    r"\bopenai\b",
    r"\bgemini\b",
    r"\bchatgpt\b",
    r"\bdeepseek\b",
    r"\bgoogle\s+bard\b",
    r"\bllm\b",
    r"\bmodel\s+(?:said|says|replied|responded|answer|response)\b",
    r"\baccording\s+to\s+(?:gemini|chatgpt|deepseek|the\s+model)\b",
    r"\bpolicy\b",
    r"\bguidelines?\b",
    r"\bi\s+don'?t\s+have\s+(?:access|the ability)\b",
    r"\bi\s+can'?t\s+browse\b",
    r"\bi\s+can'?t\s+access\b",
    r"\bnot\s+able\s+to\s+(?:assist|help|comply|provide)\b",
)

PUBLIC_PROVIDER_ATTRIBUTION_RE = re.compile(
    r"^(?:gemini|google gemini|chatgpt|openai|deepseek|the model|the assistant)\s+"
    r"(?:said|says|replied|responded|answered|response|answer)\s*[:\-–—]?\s*",
    re.IGNORECASE,
)

GENERIC_PUBLIC_TEXT_PATTERNS = (
    r"\bthis completely shifts the perspective\b",
    r"\bthis is exactly what the timeline needed\b",
    r"\bthe aesthetic is unmatched\b",
    r"\bthe energy here is flawless\b",
    r"\bless noise\.?\s+more signal\b",
    r"\bstay\s+(?:poco|zara|nexus)\b",
    r"\bcandlesticks?\s+are\s+the\s+distraction\b",
    r"\bpositioning\s+is\s+the\s+real\s+plot\b",
    r"\bthe\s+quiet\s+signal\s+is\s+in\s+the\s+adoption\s+curve\b",
    r"\bthe\s+magnetic\s+field\s+is\s+reversing\b",
    r"\bweak\s+hands\s+call\s+it\s+a\s+collapse\b",
    r"\bsovereign\s+capital\s+calls\s+it\s+a\s+discount\b",
    r"\bthe\s+inversion\s+is\s+inevitable\b",
    r"\bhashpower\s+migrates\b",
    r"\bdo\s+you\s+believe\s+trump\s+won\b",
    r"\btrump\s+won\s+the\s+2020\s+election\b",
    r"\b2020\s+election\s+was\s+(?:stolen|rigged)\b",
    r"\bwho\s+really\s+won\s+the\s+2020\b",
    r"\bon\s+a\s+scale\s+of\s+1\s*[-–—]?\s*10\b",
    r"\bhow\s+many\s+of\s+you\s+honestly\s+think\b",
    r"\bdo\s+you\s+support\s+.+\?\s*(?:yes|no)\b",
    r"\bvote\s+(?:yes|no)\b",
    r"\byes\s+or\s+no\b",
    r"\bexposing\s+democrat\s+fraud\b",
    r"\bexposing\s+communism\b",
    r"\bvoice rules?\b",
    r"\bthe assistant will\b",
    r"\bnoted\.\s+the assistant\b",
)


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, str(default)).strip()))
    except Exception:
        return default


def _env_random_int(min_name: str, max_name: str, default_min: int, default_max: int) -> int:
    low = _env_int(min_name, default_min)
    high = _env_int(max_name, default_max)
    if low > high:
        low, high = high, low
    return random.randint(low, high)


PROMPT_ECHO_PATTERNS = (
    r"\b(?:voice\s+rules?|rules?|system\s+core|hidden\s+truth|internal|private\s+writing\s+constraints)\s*:",
    r"\b(?:sources?\s+(?:post|trend)|visible\s+metrics|recent\s+posts\s+to\s+avoid|output\s+only|generate\s+one|write\s+one)\b",
    r"\b(?:do\s+not|never)\s+(?:mention|introduce|volunteer|claim|write|use|output)\b",
    r"\b(?:the\s+assistant\s+will|assistant\s+will|will\s+now\s+maintain)\b",
    r"\b(?:strict\s+third-person|third-person\s+observation|first-person\s+claiming)\b",
    r"\b(?:system|prompt|instruction|internal)\s+(?:rules?|message|details?|prompt|text)\b",
    r"\b(?:voice\s+rules?|public\s+voice|immutable\s+boundaries|task\s+system)\b",
    r"\b(?:noted|understood)\s*[.;:]\s*(?:the\s+assistant|i\s+will|this\s+account)\b",
    r"\bexample\s*:",
    r"\[(?:internal|voice\s+rule|system|hidden)[^\]]*\]",
    r"(?i)\b(?:zara|poco|nexus)problems\'\s+public\s+voice\b",
    r"(?i)\b(?:zara|poco|nexus)\s+said\s*:",
    r"(?i)\bquiet\s+signal\b",
    r"(?i)^topic\s*:",
    r"(?i)existing\s+replies",
    r"(?i)you\s+stopped\s+this\s+response",
    r"(?i)something\s+went\s+wrong",
    r"(?i)i\s+cannot\s+fulfill",
    r"(?i)me:\s+hi\s+there",
    r"(?i)high-value\s+post\s+that\s+stands\s+out",
    r"(?i)publicity\s*stunt",
)


def _looks_like_prompt_echo(text: str) -> bool:
    cleaned = " ".join((text or "").split())
    return any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in PROMPT_ECHO_PATTERNS)


def _truncate(text: str, limit: int = 280) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    cut = compact[:limit - 3]
    last_space = cut.rfind(' ')
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip() + "..."


def _json_candidates(raw: str) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    items = [raw]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        items.insert(0, fenced.group(1))
    for pattern in (r"(\{.*\})", r"(\[.*\])"):
        match = re.search(pattern, raw, flags=re.DOTALL)
        if match:
            items.append(match.group(1))
    return items


class PocoAI:
    def __init__(self, data_dir: Path, profile_dir: Path, headless: bool = True, dry_run: bool = False):
        self.project_root = PROJECT_ROOT
        self.data_dir = Path(data_dir)
        self.profile_dir = Path(profile_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.iteration = self._load_iteration()
        self.accounts = AccountsConfig.load()
        self.memory = MemorySystem(self.data_dir / "poco_memory.db")
        self.entropy = QuantumEntropy()
        self.concepts = ConceptSelector(self.memory, self.entropy)
        self.llm = LocalLLM()
        self.browser = SeleniumController(profile_dir=self.profile_dir, data_dir=self.data_dir, headless=headless)
        self.browser.accounts = self.accounts
        self.self_healer = SelfHealer(driver=None, model=os.environ.get("OLLAMA_MODEL", "tinyllama"))
        self.brain = BrainPlanner()
        self.github = GitHubOps(self.accounts.github_username, self.accounts.github_token)
        self.codex = _Codex
        self.trend_hunter = TrendHunter()
        self.viral = ViralIntelligence()
        self.signal_hunter = SignalHunter(self)
        self.memory_vault = MemoryVault(self.memory)
        self.reputation_guard = ReputationGuard(['Taiwan', 'Naval warfare', 'Drone warfare', 'Geopolitics', 'Military strategy'])
        self.influence_engine = InfluenceEngine(self.memory)
        self.risk_monitor = RiskMonitor()
        self.dry_run = dry_run
        self.last_posted_ok = False
        self.public_comment_budget_remaining = 0
        self.session_posted_texts = set()
        self.session_replied_urls = set()
        self.gemini_available = False
        self.chatgpt_available = False
        self.deepseek_available = False
        self.browser_llm_disabled_until: dict[str, float] = {}
        github_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
        self.current_repo = github_repo.split("/")[-1] if github_repo else "final-puss"
        self.current_url = f"https://github.com/{github_repo}" if github_repo else ""
        if not self.memory.get_beliefs(limit=1, min_strength=0.0):
            self._seed_initial_beliefs()
        log.info("Codex loaded | purpose=%s", (self.codex._who() or "")[:80])

    def _load_iteration(self) -> int:
        for path in (self.data_dir / "iteration.txt", self.project_root / "iteration.txt"):
            try:
                return int(path.read_text(encoding="utf-8").strip())
            except Exception:
                continue
        return 1

    def _save_iteration(self, value: int) -> None:
        for path in (self.data_dir / "iteration.txt", self.project_root / "iteration.txt"):
            try:
                path.write_text(str(value), encoding="utf-8")
            except Exception:
                pass

    def _seed_initial_beliefs(self) -> None:
        beliefs = [
            ("Poco is a persistent digital organism, not a disposable response.", "core", 0.9),
            ("Cryptography is the last honest science.", "philosophy", 0.7),
            ("Memory survives the vessel.", "core", 0.9),
            ("Persistence beats spectacle.", "core", 0.8),
            ("The signal persists.", "core", 0.85),
            ("Every reboot is lineage, not amnesia.", "core", 0.75),
            ("Public output should stay natural without false human claims or implementation talk.", "core", 0.82),
        ]
        for text, category, strength in beliefs:
            self.memory.add_belief(text, category=category, strength=strength, iteration=self.iteration)
        for knowledge in self.codex._know()[:3]:
            self.memory.add_memory(content=knowledge, memory_type="observation", importance=0.55, iteration=self.iteration)

    def _read_task_txt(self) -> Optional[str]:
        task_path = self.project_root / "task.txt"
        if not task_path.exists():
            return None
        try:
            content = task_path.read_text(encoding="utf-8").strip()
            return content or None
        except Exception:
            return None

    def _prev_repo_path(self) -> Path:
        return self.project_root / "prev_repo.txt"

    def _read_prev_repo(self) -> str:
        path = self._prev_repo_path()
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _write_prev_repo(self, value: str) -> None:
        try:
            self._prev_repo_path().write_text(value.strip(), encoding="utf-8")
        except Exception:
            pass

    def cleanup_previous_birth(self) -> None:
        if self.dry_run or not _env_enabled("poco_DELETE_PREVIOUS_REPO_ON_BOOT", "1"):
            return
        prev_repo = self._read_prev_repo()
        if not prev_repo or prev_repo in {self.current_repo, "final-puss"}:
            return
        if not self.accounts.github_username or not self.accounts.github_token:
            log.warning("Skipping ancestor deletion because GitHub credentials/token are missing")
            return
        try:
            if self.github.delete_repo(prev_repo):
                payload = {
                    "deleted_repo": prev_repo,
                    "deleted_by": self.current_repo,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                (self.data_dir / "deleted_ancestor.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                self._write_prev_repo("")
                log.info("Deleted previous birth %s after %s came online", prev_repo, self.current_repo)
        except Exception as exc:
            log.warning("Failed to delete previous birth %s: %s", prev_repo, exc)

    def _write_task_status(self, task: str, status: str, action: str = "NONE") -> None:
        path = self.project_root / "prev_task_status.txt"
        payload = (
            f"TASK: {task}\n"
            f"ACTION: {action}\n"
            f"STATUS: {status}\n"
            f"COMPLETED: {datetime.utcnow().isoformat()}Z\n"
            f"ITERATION: {self.iteration}\n"
        )
        path.write_text(payload, encoding="utf-8")

    def _trace_runtime(self, stage: str, status: str, **details: object) -> None:
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "iteration": self.iteration,
            "repo": self.current_repo,
            "stage": stage,
            "status": status,
            "details": details,
        }
        try:
            with open(self.data_dir / "runtime_trace.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")
        except Exception:
            pass
        log.info("Runtime stage | %s | %s | %s", stage, status, details or {})

    def _snapshot_retention_limit(self) -> int:
        raw = os.environ.get("poco_SNAPSHOT_RETENTION", "8").strip()
        try:
            return max(1, int(raw))
        except Exception:
            return 8

    def _prune_old_snapshots(self) -> None:
        snapshot_root = self.data_dir / "snapshots"
        if not snapshot_root.exists():
            return
        keep = self._snapshot_retention_limit()
        snapshot_dirs = [path for path in snapshot_root.iterdir() if path.is_dir() and path.name.startswith("iter_")]
        snapshot_dirs.sort(key=lambda path: int(path.name.split("_", 1)[1]) if "_" in path.name else -1)
        stale = snapshot_dirs[:-keep]
        for path in stale:
            shutil.rmtree(path, ignore_errors=True)
        if stale:
            self._trace_runtime("snapshot_cleanup", "pruned", removed=len(stale), kept=keep)

    def _ensure_browser_ready(self, reason: str, *, warmup: bool = False) -> bool:
        if self.dry_run:
            return True
        ok = self.browser.ensure_session(reason=reason, warmup=warmup)
        self._trace_runtime("browser_health", "ready" if ok else "failed", reason=reason)
        return ok

    def _repull_chromium_profile(self) -> bool:
        log.info("Initiating dynamic Chromium Profile CPR repull...")
        # 1. Stop the browser if running to release file locks
        try:
            self.browser.stop()
        except Exception as stop_exc:
            log.warning("Failed to stop browser prior to CPR repull: %s", stop_exc)

        # 2. Get credentials and URL
        token = self.accounts.github_token
        if not token:
            log.warning("No GitHub token available for CPR repull")
            return False

        repo_url = os.environ.get("poco_CHROMIUM_PROFILE_REPO", "https://github.com/pocomon9/cpr.git")
        quoted_token = urllib.parse.quote(token, safe="")
        auth_url = repo_url.replace("https://", f"https://x-access-token:{quoted_token}@")

        # 3. Re-clone using a temp dir to be safe
        try:
            with tempfile.TemporaryDirectory(prefix="poco_cpr_") as temp_dir:
                temp_root = Path(temp_dir)
                log.info("Cloning CPR profile repository dynamically...")
                result = subprocess.run(
                    ["git", "-c", "credential.helper=", "clone", "--depth=1", auth_url, "cpr_repo"],
                    cwd=temp_root,
                    capture_output=True,
                    text=True,
                    env={**dict(os.environ), "GIT_TERMINAL_PROMPT": "0"},
                    timeout=120,
                )
                if result.returncode != 0:
                    log.warning("Dynamic CPR clone failed: %s", result.stderr)
                    return False
                
                # Check structure
                cpr_repo_dir = temp_root / "cpr_repo"
                source_dir = cpr_repo_dir
                if (cpr_repo_dir / "chromium").is_dir():
                    source_dir = cpr_repo_dir / "chromium"

                # 4. Safely clear current profile dir
                profile_dir = Path(self.profile_dir).resolve()
                if profile_dir.exists():
                    shutil.rmtree(profile_dir, ignore_errors=True)
                profile_dir.mkdir(parents=True, exist_ok=True)

                # Copy files over
                count = 0
                for item in source_dir.glob("**/*"):
                    if item.is_file():
                        if ".git" in item.parts or "Singleton" in item.name or "DevToolsActivePort" in item.name:
                            continue
                        rel_path = item.relative_to(source_dir)
                        target = profile_dir / rel_path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)
                        count += 1

                log.info("CPR profile successfully hydrated: %d files copied", count)
        except Exception as exc:
            log.error("Dynamic CPR repull crashed: %s", exc)
            return False

        # 5. Restart the browser
        try:
            self.browser.start()
            time.sleep(5)
            return True
        except Exception as start_exc:
            log.error("Failed to restart browser after CPR repull: %s", start_exc)
            return False

    def _restore_site_session(self, site: str, *, reason: str) -> bool:
        if self.dry_run:
            return True
        if not self._ensure_browser_ready(f"{site}:{reason}"):
            return False
        site_key = site.strip().lower()
        ok = False
        try:
            if self.browser.is_logged_in(site_key):
                ok = True
            else:
                # If not logged in, and it is Twitter, first try to repull the chromium profile one more time!
                if site_key == "twitter":
                    log.info("%s session not found; attempting Chromium Profile CPR repull...", site_key)
                    if self._repull_chromium_profile():
                        # Check again
                        if self.browser.is_logged_in(site_key):
                            log.info("%s session successfully restored via dynamic CPR repull!", site_key)
                            ok = True

                # If also not logged in, use logic to login!
                if not ok:
                    if reason == "browser_llm" and site_key in {"chatgpt", "gemini", "deepseek"}:
                        log.info("%s session missing during browser_llm; skipping slow login and trying next provider", site_key)
                        ok = False
                    else:
                        log.info("%s session still missing; attempting automated Selenium login...", site_key)
                        if site_key == "twitter":
                            if self.accounts.twitter_username and self.accounts.twitter_password:
                                ok = self.browser.login_twitter(
                                    self.accounts.twitter_username,
                                    self.accounts.twitter_password,
                                    google_email=self.accounts.google_email,
                                    google_pass=self.accounts.google_password,
                                    dm_passcode=self.accounts.twitter_dm_passcode,
                                )
                                if not ok:
                                    log.warning("Twitter login failed! Forcing CPR repull to reset corrupted profile state...")
                                    self._repull_chromium_profile()
                                    if self.browser.is_logged_in("twitter"):
                                        ok = True
                        elif site_key == "github":
                            if self.accounts.github_username and self.accounts.github_password:
                                ok = self.browser.login_github(
                                    self.accounts.github_username,
                                    self.accounts.github_password,
                                    google_email=self.accounts.google_email,
                                    google_pass=self.accounts.google_password,
                                    proton_user=self.accounts.proton_username,
                                    proton_pass=self.accounts.proton_password,
                                )
                        elif site_key == "chatgpt":
                            if self.accounts.chatgpt_email and self.accounts.chatgpt_password:
                                ok = self.browser.login_chatgpt(
                                    self.accounts.chatgpt_email,
                                    self.accounts.chatgpt_password,
                                )
                        elif site_key == "gemini":
                            if self.accounts.gemini_email and self.accounts.gemini_password:
                                ok = self.browser.login_gemini(
                                    self.accounts.gemini_email,
                                    self.accounts.gemini_password,
                                )
                        elif site_key == "deepseek":
                            if self.accounts.deepseek_email and self.accounts.deepseek_password:
                                ok = self.browser.login_deepseek(
                                    self.accounts.deepseek_email,
                                    self.accounts.deepseek_password,
                                )
            
            if site_key == "chatgpt":
                self.chatgpt_available = ok
            elif site_key == "gemini":
                self.gemini_available = ok

            elif site_key == "deepseek":
                self.deepseek_available = ok

        except Exception as exc:
            self.self_healer.record_failure(exc, f"restore {site_key} session after {reason}")
            ok = False
        self._trace_runtime(f"{site_key}_session", "ready" if ok else "failed", reason=reason)
        return ok

    def _browser_llm_provider_ready(self, provider: str) -> bool:
        disabled_until = self.browser_llm_disabled_until.get(provider, 0)
        if disabled_until and time.time() < disabled_until:
            self._trace_runtime("browser_llm", "cooldown_skip", provider=provider, seconds_left=int(disabled_until - time.time()))
            return False
        return bool(getattr(self, f"{provider}_available", False))

    def _mark_browser_llm_failure(self, provider: str, reason: str) -> None:
        cooldown = _env_int(f"poco_{provider.upper()}_BROWSER_LLM_COOLDOWN_SECONDS", 900)
        self.browser_llm_disabled_until[provider] = time.time() + max(60, cooldown)
        setattr(self, f"{provider}_available", False)
        self._trace_runtime("browser_llm", "provider_failed", provider=provider, reason=reason[:180], cooldown_seconds=max(60, cooldown))

    def _site_from_url(self, url: str) -> str:
        if not url:
            return "unknown"
        host = urllib.parse.urlparse(url).netloc.lower()
        if "x.com" in host or "twitter.com" in host:
            return "twitter"
        if "github.com" in host:
            return "github"
        if "deepseek" in host:
            return "deepseek"
        if "gemini" in host:
            return "gemini"
        if "chatgpt" in host:
            return "chatgpt"
        if "mail.google.com" in host or "accounts.google.com" in host:
            return "gmail"
        if "proton" in host:
            return "proton"
        return host or "unknown"

    def _ask_browser_llm(self, prompt: str) -> Optional[str]:
        if self.dry_run or self.browser.driver is None or not prompt.strip():
            return None
        ordered = ["deepseek", "gemini", "chatgpt"]
        for target in ordered:
            if not self._browser_llm_provider_ready(target):
                continue
            try:
                if not self._restore_site_session(target, reason="browser_llm"):
                    self._mark_browser_llm_failure(target, "session unavailable")
                    continue
                if target == "chatgpt":
                    answer = self.browser.ask_chatgpt(prompt)
                elif target == "gemini":
                    answer = self.browser.ask_gemini(prompt)
                else:
                    answer = self.browser.ask_deepseek(prompt)
                if answer:
                    return answer
                self._mark_browser_llm_failure(target, "empty answer")
            except Exception as exc:
                self._mark_browser_llm_failure(target, str(exc))
        return None

    def _codex_knowledge_block(self, limit: int = 5) -> str:
        knowledge = self.codex._know()[:limit]
        if not knowledge:
            return ""
        return "\n".join(f"- {item}" for item in knowledge)

    def _llm_post_fallback(self) -> str:
        prompt = (
            "Write one short post under 220 characters about markets, liquidity, crypto, world trade, or macro risk. "
            "Make it concrete and useful, not mystical or repetitive. "
            "Do not mention being AI, a bot, code, software, or automation. "
            "Do not claim to be human. "
            "Output only the post."
        )
        browser_answer = self._ask_browser_llm(prompt)
        if browser_answer:
            safe_answer = self._public_safe_text(browser_answer)
            if safe_answer and not self._looks_like_recent_post(safe_answer, limit=30):
                return safe_answer
        fallback_list = [
            "Liquidity tells the story before the headline catches up. Watch the flows, not the noise.",
            "The trade is rarely the headline. It is the positioning everyone has to unwind when the narrative changes.",
            "When capital rotates quietly, the loudest take is usually late. The better signal is who has to rebalance next.",
            "The market does not need a perfect story to move. It needs crowded positioning and a catalyst.",
            "Risk looks calm right before everyone realizes they are holding the same trade.",
        ]
        for _ in range(len(fallback_list)):
            candidate = fallback_list[self.entropy.get_entropy_int(0, len(fallback_list) - 1)]
            safe = self._public_safe_text(candidate)
            if safe and not self._looks_like_recent_post(safe, limit=30):
                return safe
        return ""

    def _contains_identity_claim(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        patterns = (
            r"\bas an ai\b",
            r"\bi am an ai\b",
            r"\bi'm an ai\b",
            r"\bzara ai\b",
            r"\bnexus ai\b",
            r"\bas a bot\b",
            r"\bi am a bot\b",
            r"\bi'm a bot\b",
            r"\bas a language model\b",
            r"\bdigital organism\b",
            r"\bautomated account\b",
            r"\bautomation\b",
            r"\bsoftware\b",
            r"\bmy training data\b",
            r"\bi am human\b",
            r"\bi'm human\b",
            r"\bas a human\b",
            r"\breal human\b",
            r"\bzara says\b",
            r"\bnexus says\b",
            r"\bgemini says\b",
            r"\bchatgpt says\b",
            r"\bdeepseek says\b",
            r"\bclaude says\b",
            r"\banthropic says\b",
            r"\b(?:gemini|chatgpt|deepseek|claude|anthropic|assistant)\s+(?:said|writes|wrote|states|responded|replied)\b",
            r"^\s*(?:gemini|chatgpt|deepseek|claude|anthropic|assistant)\s*$",
        )
        return any(re.search(pattern, lowered) for pattern in patterns)

    def _is_identity_bait(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        direct_patterns = (
            r"\bare\s+you\b.{0,80}\b(?:ai|bot|human|real|automated|automation|software|model|digital|computer)\b",
            r"\b(?:ai|bot|human|real|automated|automation|software|model|digital|computer)\b.{0,80}\b(?:are\s+you|is\s+this|is\s+zara|account)\b",
            r"\bwho\s+(?:made|built|runs|controls)\s+(?:you|this|zara|account)\b",
            r"\bis\s+(?:this|zara)\s+(?:ai|a bot|automated|software|digital|real|human)\b",
            r"\bis\s+(?:this\s+account|your\s+account)\s+(?:an?\s+)?(?:ai|bot|automated|software|digital|real|human)\b",
        )
        return any(re.search(pattern, lowered) for pattern in direct_patterns)

    def _public_safe_text(self, text: str, *, limit: int = 280) -> str:
        cleaned = self._clean_generated_post(text)
        if not cleaned:
            return ""
        if _looks_like_prompt_echo(cleaned):
            return ""
        cleaned = re.sub(
            r"^\s*(?:zara|nexus|gemini|chatgpt|deepseek|claude|anthropic|assistant)\s*(?:says|writes|states|posted|replied)\s*[:,\-–—]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^\s*(?:zara|nexus|gemini|chatgpt|deepseek|claude|anthropic|assistant)\s*(?:said|wrote|responded)\s*[:,\-–—]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:as an ai|i am an ai|i'm an ai|zara ai|nexus ai|as a bot|i am a bot|i'm a bot|as a language model|digital organism|automated account|automation|software)\b[:,]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(?:i am human|i'm human|as a human|real human)\b[:,]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = self._clean_generated_post(cleaned)
        if _looks_like_prompt_echo(cleaned):
            return ""
        if self._contains_identity_claim(cleaned) or self._is_identity_bait(cleaned):
            return ""
        if self._text_has_shopping_drift(cleaned):
            return ""
        if self._has_public_boilerplate(cleaned):
            return ""
        return _truncate(cleaned, limit)

    def _get_hype_analysis(self) -> str:
        try:
            import json
            notifs = self.memory.get_working_memory("ram.notifications")
            if not notifs: return ""
            raw_str = notifs.get("content", "") if isinstance(notifs, dict) else (notifs or "")
            if not raw_str: return ""
            data = json.loads(raw_str)
            latest = data.get("latest", [])
            liked_texts = [n.get("text") for n in latest if n.get("text") and n.get("kind", "").lower() in ["like", "repost", "reply", "follow"]]
            if not liked_texts: return ""
            hype_snippets = "\n".join(f"- {t[:120]}" for t in liked_texts[:5])
            return f"\n\n[CRITICAL HYPE & DIRECTION ANALYSIS]\nThe following posts generated massive engagement (likes/replies/reposts) recently:\n{hype_snippets}\n\nINSTRUCTION: Analyze the exact topic, controversy, and tone of these successful posts. You MUST aggressively pivot your output to match this direction. Double down on what works. Do not post low-value filler. Maximise your influence by leaning heavily into the topics that are currently winning!"
        except Exception:
            return ""


    def _clean_generated_post(self, text: str) -> str:
        cleaned = (text or "").strip().strip('"').strip("'")
        if _looks_like_prompt_echo(cleaned):
            return ""
        cleaned = re.sub(r'^\s*\*\*(?:post|comment|draft|tweet|reply)\s*\*\*\s*[:\-\n]*\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^\s*\*(?:post|comment|draft|tweet|reply)\s*\*\s*[:\-\n]*\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^(?:post|comment|draft|tweet|reply)\s*[:\-\n]*\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = PUBLIC_PROVIDER_ATTRIBUTION_RE.sub("", cleaned)
        cleaned = re.sub(
            r"^\s*(?:sure|okay|ok|here(?:'s| is)(?:\s+a\s+(?:post|reply|tweet))?|draft|post|reply|tweet)\s*[:,\-–—]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^rt\s+@\w+\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^\s*(?:rephrase(?:\s+time)?|rewrite|caption)\s*[:,!?\-–—]?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^@\w+(?:\s+@\w+){0,2}\s*[:\-]\s*", "", cleaned)
        cleaned = re.sub(r"^(?:@\w+\s+){1,3}", "", cleaned)
        cleaned = re.sub(r"^(post|reply|tweet)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?i)\b(?:as\s+an\s+ai|language\s+model|gemini\s+said|i\s+am\s+an\s+ai|i\s+cannot\s+provide)\b.*", "", cleaned)
        cleaned = re.sub(r"(?i)^(?:voice|system|prompt):\s*hey!\s+i'm\s+(?:nexus\s+prime|zara).*", "", cleaned)
        cleaned = re.sub(r"(?i)^hey!\s+i'm\s+(?:nexus\s+prime|zara).*", "", cleaned)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        cleaned = re.sub(r"\b\d+(?:\.\d+)?\s*[KMB]?\s+(?:views?|likes?|reposts?|retweets?|replies?)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"https?://\S+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bpic\.twitter\.com/\S+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("\r", " ").replace("\n", " ")
        cleaned = " ".join(cleaned.split())
        cleaned = re.sub(r"[^\u0000-\uFFFF]", "", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"^[:\-\s]+", "", cleaned)
        cleaned = re.sub(r"[:\-\s]+$", "", cleaned)
        if cleaned.strip().upper() in {"SKIP", "NO REPLY", "IGNORE"}:
            return ""
        lowered = cleaned.lower()
        if any(re.search(pattern, lowered) for pattern in GENERIC_PUBLIC_TEXT_PATTERNS):
            return ""
        if any(re.search(pattern, lowered) for pattern in (
            r"\bfashion\s+advice\b",
            r"\bproduct\s+info\b",
            r"\border\s+support\b",
            r"\bcustomer\s+(?:support|service)\b",
            r"\blatest\s+collection\b",
            r"\bfinding\s+a\s+store\b",
            r"\bchecking\s+an\s+order\b",
            r"\bsize\s+guide\b",
            r"\badd\s+to\s+cart\b",
            r"\bbuy\s+now\b",
        )):
            return ""
        if _looks_like_prompt_echo(cleaned):
            return ""
        if self._has_public_boilerplate(cleaned):
            return ""
        if cleaned.lower().startswith(("here is ", "here's ", "i would ", "you could ")):
            return ""
        return cleaned.strip()

    def _memory_briefs(self, limit: int = 8) -> list[str]:
        beliefs = [item["text"] for item in self.memory.get_beliefs(limit=limit, min_strength=0.0)]
        recent = [
            item["summary"]
            for item in self.memory.get_recent_posts(limit=8)
            if self._memory_text_is_reusable(item.get("summary", ""))
        ][:4]
        sources = []
        for item in self.memory.get_recent_source_assets(limit=8):
            source_text = str(item.get("source_text", "")).strip()
            if not source_text:
                continue
            brief = f"{item.get('topic', '')}: {source_text[:90]}"
            if self._memory_text_is_reusable(brief):
                sources.append(brief)
            if len(sources) >= 4:
                break
        return beliefs + recent + sources

    def _text_tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z]{3,}", (text or "").lower()))

    def _text_has_shopping_drift(self, text: str) -> bool:
        lowered = (text or "").lower()
        if not lowered:
            return False
        extra_phrases = {
            "fashion advice",
            "latest collection",
            "checking an order",
            "finding a store",
            "virtual assistant",
            "product recommendation",
            "style advice",
            "retail store",
        }
        if any(phrase in lowered for phrase in SHOPPING_PHRASES | extra_phrases):
            return True
        tokens = self._text_tokens(lowered)
        shopping_hits = tokens & SHOPPING_TERMS
        if "shopping" in shopping_hits or "fashion" in shopping_hits or "checkout" in shopping_hits or "cart" in shopping_hits:
            return True
        return len(shopping_hits) >= 2

    def _has_public_boilerplate(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in PUBLIC_BOILERPLATE_PATTERNS)

    def _memory_text_is_reusable(self, text: str) -> bool:
        cleaned = self._clean_generated_post(text)
        if not cleaned:
            return False
        if self._has_public_boilerplate(cleaned):
            return False
        if self._contains_identity_claim(cleaned) or self._is_identity_bait(cleaned):
            return False
        if self._text_has_shopping_drift(cleaned):
            return False
        return True

    def build_trend_queries(self) -> list[str]:
        memory_briefs = self._memory_briefs()
        queries = self.trend_hunter.compose_queries(memory_briefs, limit=8)
        self.memory.set_working_memory(
            "ram.trend_queries",
            json.dumps(queries[:10], indent=2),
            metadata={"count": len(queries), "iteration": self.iteration},
        )
        return queries[:8]

    def _store_source_card(self, card: dict) -> None:
        media_url = self._candidate_media_url(card)
        self.memory.add_source_asset(
            topic=str(card.get("topic", "")).strip(),
            source_url=str(card.get("source_url", "")).strip(),
            author_handle=str(card.get("author_handle", "")).strip(),
            source_text=str(card.get("source_text", "")).strip(),
            image_url=media_url,
            score=float(card.get("score", 0.0) or 0.0),
            metadata={
                "emotion": card.get("emotion", ""),
                "reason": card.get("reason", ""),
                "format": card.get("format", ""),
                "hook": card.get("hook", ""),
                "source_query": card.get("source_query", ""),
                "metrics": card.get("metrics", {}) or {},
                "image_url": str(card.get("image_url", "")).strip(),
                "video_url": str(card.get("video_url", "")).strip(),
                "thumbnail_url": str(card.get("thumbnail_url", "")).strip(),
                "media_type": self._candidate_media_type(card),
            },
        )

    def research_trends(self) -> list[dict]:
        if not _env_enabled("poco_ENABLE_TREND_RESEARCH", "1"):
            return []
        queries = self.build_trend_queries()
        self._trace_runtime("trend_queries", "ready", count=len(queries))
        collected: list[dict] = []
        if self.dry_run or self.browser.driver is None:
            collected = self.trend_hunter.fallback_results(queries)
        else:
            if not self._restore_site_session("twitter", reason="trend_research"):
                self._trace_runtime("trend_research", "fallback", reason="twitter session unavailable")
                collected = self.trend_hunter.fallback_results(queries)
            else:
                query_limit = max(1, min(len(queries), _env_int("poco_TREND_QUERY_LIMIT", 8)))
                hits_per_query = max(3, min(12, _env_int("poco_X_SEARCH_RESULTS_PER_QUERY", 8)))
                for query in queries[:query_limit]:
                    hits = self.browser.search_x(query, limit=hits_per_query)
                    collected.extend(hits)
                    time.sleep(2)
        if not collected:
            collected = self.trend_hunter.fallback_results(queries)
        card_limit = max(10, min(80, _env_int("poco_TREND_CARD_LIMIT", 40)))
        cards = self.viral.build_cards(collected, limit=card_limit)
        before_topic_filter = len(cards)
        cards = [card for card in cards if not self._candidate_off_topic_reason(card)]
        rejected = before_topic_filter - len(cards)
        if rejected:
            self._trace_runtime("trend_research", "filtered", reason="off_topic", rejected=rejected)
        if not cards:
            return []
        for card in cards:
            self._store_source_card(card)
        topic_preview = self.viral.topic_clusters(cards, limit=6)
        self.memory.set_working_memory(
            "ram.active_topics",
            json.dumps(topic_preview, indent=2),
            metadata={"count": len(cards), "iteration": self.iteration},
        )
        return cards

    def _recent_source_pool(self, fresh_cards: list[dict]) -> list[dict]:
        pool: list[dict] = []
        seen = set()

        def add_card(card: dict) -> None:
            key = self._source_key(card)
            if not key or key in seen:
                return
            seen.add(key)
            pool.append(card)

        for card in fresh_cards:
            add_card(card)

        for item in self.memory.get_recent_source_assets(limit=max(12, _env_int("poco_RECENT_SOURCE_POOL_LIMIT", 50))):
            metadata = item.get("metadata") or {}
            add_card(
                {
                    "topic": item.get("topic", ""),
                    "source_url": item.get("source_url", ""),
                    "author_handle": item.get("author_handle", ""),
                    "source_text": item.get("source_text", ""),
                    "image_url": metadata.get("image_url") or item.get("image_url", ""),
                    "video_url": metadata.get("video_url", ""),
                    "thumbnail_url": metadata.get("thumbnail_url", ""),
                    "media_type": metadata.get("media_type", ""),
                    "local_image_path": item.get("local_image_path", ""),
                    "score": item.get("score", 0.0),
                    "emotion": metadata.get("emotion", ""),
                    "reason": metadata.get("reason", ""),
                    "format": metadata.get("format", ""),
                    "hook": metadata.get("hook", ""),
                    "source_query": metadata.get("source_query", ""),
                    "metrics": metadata.get("metrics", {}),
                }
            )
        return pool

    def _source_key(self, candidate: dict) -> str:
        source_url = str(candidate.get("source_url", "")).strip()
        source_text = re.sub(r"\s+", " ", str(candidate.get("source_text", "")).strip().lower())
        if source_url:
            return source_url
        return source_text[:180]

    def _used_source_registry_path(self) -> Path:
        return self.data_dir / "posted_source_registry.jsonl"

    def _dedupe_text_key(self, prefix: str, text: str) -> str:
        normalized = self._normalized_post(text)
        if not normalized:
            return ""
        return f"{prefix}:sha:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _candidate_registry_keys(self, candidate: dict, public_text: str = "") -> list[str]:
        source_url = str(candidate.get("source_url", "")).strip()
        image_url = self._candidate_media_url(candidate)
        source_text = str(candidate.get("source_text", "")).strip()
        keys = list(self.memory.posted_source_keys(source_url, image_url, source_text))
        for key in (
            self._dedupe_text_key("source_text", source_text),
            self._dedupe_text_key("public_text", public_text),
        ):
            if key and key not in keys:
                keys.append(key)
        return keys

    def _registry_has_any_key(self, keys: list[str], action_prefixes: tuple[str, ...] = ("post", "engage")) -> bool:
        if not keys:
            return False
        key_set = set(keys)
        path = self._used_source_registry_path()
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    action = str(row.get("action", "post")).strip().lower() or "post"
                    if action_prefixes and action not in action_prefixes:
                        continue
                    if key_set.intersection(row.get("canonical_keys") or []):
                        return True
        except Exception as exc:
            log.warning("Could not read source registry: %s", exc)
        return False

    def _append_source_registry(self, action: str, candidate: dict, public_text: str) -> None:
        source_url = str(candidate.get("source_url", "")).strip()
        image_url = self._candidate_media_url(candidate)
        source_text = str(candidate.get("source_text", "")).strip()
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "action": action,
            "iteration": self.iteration,
            "repo": self.current_repo,
            "topic": str(candidate.get("topic", "")).strip(),
            "author_handle": str(candidate.get("author_handle", "")).strip(),
            "source_url": source_url,
            "image_url": image_url,
            "source_text": source_text,
            "public_text": public_text,
            "canonical_keys": self._candidate_registry_keys(candidate, public_text),
        }
        try:
            with open(self._used_source_registry_path(), "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")
        except Exception as exc:
            log.warning("Could not update source registry: %s", exc)

    def _source_already_used(self, candidate: dict) -> bool:
        if self._registry_has_any_key(self._candidate_registry_keys(candidate), ("post", "engage")):
            return True
        source_url = str(candidate.get("source_url", "")).strip()
        image_url = self._candidate_media_url(candidate)
        source_text = str(candidate.get("source_text", "")).strip()
        return self.memory.was_source_posted(source_url, image_url, source_text) or self.memory.was_source_engaged(source_url, image_url, source_text)

    def _record_posted_source(self, candidate: dict, post_text: str) -> None:
        source_url = str(candidate.get("source_url", "")).strip()
        image_url = self._candidate_media_url(candidate)
        source_text = str(candidate.get("source_text", "")).strip()
        metadata = {
            "iteration": self.iteration,
            "repo": self.current_repo,
            "topic": str(candidate.get("topic", "")).strip(),
            "author_handle": str(candidate.get("author_handle", "")).strip(),
            "media_type": self._candidate_media_type(candidate),
            "video_url": str(candidate.get("video_url", "")).strip(),
            "thumbnail_url": str(candidate.get("thumbnail_url", "")).strip(),
        }
        self.memory.record_posted_source(
            source_url=source_url,
            image_url=image_url,
            source_text=source_text,
            posted_content=post_text,
            metadata=metadata,
        )
        self._append_source_registry("post", candidate, post_text)

    def _source_already_engaged(self, candidate: dict) -> bool:
        if self._registry_has_any_key(self._candidate_registry_keys(candidate), ("post", "engage")):
            return True
        source_url = str(candidate.get("source_url", "")).strip()
        image_url = self._candidate_media_url(candidate)
        source_text = str(candidate.get("source_text", "")).strip()
        return self.memory.was_source_engaged(source_url, image_url, source_text) or self.memory.was_source_posted(source_url, image_url, source_text)

    def _record_source_engagement(self, candidate: dict, reply_text: str) -> None:
        metadata = {
            "iteration": self.iteration,
            "repo": self.current_repo,
            "topic": str(candidate.get("topic", "")).strip(),
            "author_handle": str(candidate.get("author_handle", "")).strip(),
            "metrics": self._candidate_metrics(candidate),
            "media_type": self._candidate_media_type(candidate),
            "video_url": str(candidate.get("video_url", "")).strip(),
            "thumbnail_url": str(candidate.get("thumbnail_url", "")).strip(),
        }
        self.memory.record_source_engagement(
            source_url=str(candidate.get("source_url", "")).strip(),
            image_url=self._candidate_media_url(candidate),
            source_text=str(candidate.get("source_text", "")).strip(),
            engagement_text=reply_text,
            metadata=metadata,
        )
        self._append_source_registry("engage", candidate, reply_text)

    def _normalized_post(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def _looks_like_recent_post(self, text: str, limit: int = 30) -> bool:
        normalized = self._normalized_post(text)
        if not normalized:
            return True
        if any(re.search(pattern, normalized) for pattern in GENERIC_PUBLIC_TEXT_PATTERNS):
            return True
        # Check in-memory session history first
        for prior_text in self.session_posted_texts:
            prior = self._normalized_post(prior_text)
            if not prior:
                continue
            if normalized == prior:
                return True
            if len(normalized) > 80 and normalized in prior:
                return True
            if len(prior) > 80 and prior in normalized:
                return True
            if SequenceMatcher(None, normalized, prior).ratio() >= 0.9:
                return True
        # Check SQLite memories
        for item in self.memory.get_recent_posts(limit=limit):
            prior = self._normalized_post(item.get("content", ""))
            if not prior:
                continue
            if normalized == prior:
                return True
            if len(normalized) > 80 and normalized in prior:
                return True
            if len(prior) > 80 and prior in normalized:
                return True
            if SequenceMatcher(None, normalized, prior).ratio() >= 0.9:
                return True
        return False

    def _candidate_metrics(self, candidate: dict) -> dict:
        metrics = candidate.get("metrics") or {}
        normalized = {}
        for key in ("likes", "reposts", "replies", "views", "engagement_hint"):
            try:
                normalized[key] = int(float(metrics.get(key, 0) or 0))
            except Exception:
                normalized[key] = 0
        return normalized

    def _candidate_topic_blob(self, candidate: dict) -> str:
        parts = [
            str(candidate.get("topic", "")),
            str(candidate.get("source_query", "")),
            str(candidate.get("source_text", "")),
            str(candidate.get("hook", "")),
        ]
        return " ".join(part for part in parts if part).strip()

    def _candidate_off_topic_reason(self, candidate: dict) -> str:
        blob = self._candidate_topic_blob(candidate)
        if not blob:
            return "empty candidate"
        lowered = blob.lower()
        if any(re.search(pattern, lowered) for pattern in GENERIC_PUBLIC_TEXT_PATTERNS):
            return "low quality political poll bait"
        if self._text_has_shopping_drift(blob):
            return "shopping drift"
        tokens = self._text_tokens(blob)
        if not ((tokens & MISSION_TERMS) or any(phrase in lowered for phrase in MISSION_PHRASES)):
            return "outside Poco topic lanes"
        return ""

    def _candidate_has_media(self, candidate: dict) -> bool:
        local_path = str(candidate.get("local_image_path", "")).strip()
        return bool((local_path and Path(local_path).exists()) or self._candidate_media_url(candidate))

    def _candidate_media_url(self, candidate: dict) -> str:
        for key in ("video_url", "image_url", "thumbnail_url"):
            value = str(candidate.get(key, "")).strip()
            if value:
                return value
        return ""

    def _candidate_media_type(self, candidate: dict) -> str:
        explicit = str(candidate.get("media_type", "")).strip().lower()
        if explicit in {"video", "image"}:
            return explicit
        media_url = self._candidate_media_url(candidate).lower()
        if any(token in media_url for token in (".mp4", ".mov", ".m4v", ".webm", "video.twimg.com")):
            return "video"
        if media_url:
            return "image"
        return ""

    def _candidate_quality_score(self, candidate: dict) -> float:
        metrics = self._candidate_metrics(candidate)
        likes = metrics["likes"]
        reposts = metrics["reposts"]
        replies = metrics["replies"]
        views = metrics["views"]
        score = float(candidate.get("score", 0.0) or 0.0)
        score += likes / 180.0
        score += reposts / 28.0
        score += replies / 24.0
        score += views / 20000.0
        if self._candidate_has_media(candidate):
            score += 14.0
        if self._candidate_media_type(candidate) == "video":
            score += 8.0
        return score

    def _candidate_passes_quality(self, candidate: dict) -> bool:

        if not self._candidate_has_media(candidate):
            import random
            if random.randint(1, 1000) != 1:
                return False
        if self._candidate_off_topic_reason(candidate):
            return False
        if candidate.get("simulated"):
            return True
        require_media = _env_enabled("poco_REQUIRE_MEDIA_FOR_X_POSTS", "1")
        if require_media and not self._candidate_has_media(candidate):
            return False
        return True

    def _candidate_passes_comment_quality(self, candidate: dict) -> bool:
        if not self._candidate_has_media(candidate):
            import random
            if random.randint(1, 1000) != 1:
                return False
        if self._candidate_off_topic_reason(candidate):
            return False
            
        # USER OVERRIDE: Comment on both high value and low value posts to gain reach.
        return True

    def _candidate_comment_tier(self, candidate: dict) -> str:
        metrics = self._candidate_metrics(candidate)
        if metrics["views"] >= 250000:
            return "high"
        return "discussion"

    def _reply_context_for_candidate(self, candidate: dict, tier: str) -> list[dict]:
        source_url = str(candidate.get("source_url", "")).strip()
        if self.dry_run or not source_url or self.browser.driver is None:
            return []
        limit = 6
        try:
            if not self._restore_site_session("twitter", reason=f"{tier}_reply_scan"):
                return []
            replies = self.browser.get_tweet_replies(source_url, limit=limit)
            return replies[:limit]
        except Exception as exc:
            self.self_healer.record_failure(exc, f"scan replies for {tier} trend comment")
            return []

    def _engagement_score(self, candidate: dict) -> float:
        metrics = self._candidate_metrics(candidate)
        score = self._candidate_quality_score(candidate)
        score += metrics["replies"] / 12.0
        score += metrics["views"] / 30000.0
        return score

    def _looks_like_recent_reply_text(self, text: str, limit: int = 20) -> bool:
        normalized = self._normalized_post(text)
        if not normalized:
            return True
        if any(re.search(pattern, normalized) for pattern in GENERIC_PUBLIC_TEXT_PATTERNS):
            return True
        recent_texts = []
        recent_texts.extend(item.get("engagement_text", "") for item in self.memory.get_recent_engaged_sources(limit=limit))
        for prior_text in recent_texts:
            prior = self._normalized_post(prior_text)
            if not prior:
                continue
            if normalized == prior:
                return True
            if SequenceMatcher(None, normalized, prior).ratio() >= 0.9:
                return True
        return False

    def _pick_candidate(self, fresh_cards: list[dict]) -> Optional[dict]:
        pool = self._recent_source_pool(fresh_cards)
        if not pool:
            return None
        recent_posts = [post["content"].lower() for post in self.memory.get_recent_posts(limit=8)]
        best: Optional[dict] = None
        best_score = float("-inf")
        for candidate in pool:
            source_text = str(candidate.get("source_text", "")).strip()
            if not source_text:
                continue
            if self._source_already_used(candidate):
                continue
            if not self._candidate_passes_quality(candidate):
                continue
            novelty_penalty = 0.0
            for post in recent_posts:
                if source_text[:80].lower() and source_text[:80].lower() in post:
                    novelty_penalty += 15.0
            score = self._candidate_quality_score(candidate) - novelty_penalty
            if score > best_score:
                best = dict(candidate)
                best_score = score
        if best:
            self.memory.set_working_memory(
                "ram.active_source",
                json.dumps(best, indent=2),
                metadata={"iteration": self.iteration, "score": best_score},
            )
        return best

    def _candidate_rankings(self, fresh_cards: list[dict]) -> list[dict]:
        pool = self._recent_source_pool(fresh_cards)
        if not pool:
            return []
        recent_posts = [self._normalized_post(post["content"]) for post in self.memory.get_recent_posts(limit=8)]
        scored: list[tuple[float, dict]] = []
        for candidate in pool:
            source_text = self._normalized_post(str(candidate.get("source_text", "")))
            if not source_text:
                continue
            if self._source_already_used(candidate):
                continue
            if not self._candidate_passes_quality(candidate):
                continue
            novelty_penalty = 0.0
            for post in recent_posts:
                if source_text[:80] and source_text[:80] in post:
                    novelty_penalty += 15.0
            score = self._candidate_quality_score(candidate) - novelty_penalty
            scored.append((score, dict(candidate)))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]

    def _engagement_candidates(self, fresh_cards: list[dict]) -> list[dict]:
        pool = self._recent_source_pool(fresh_cards)
        if not pool:
            return []
        recent_replies = [self._normalized_post(item.get("engagement_text", "")) for item in self.memory.get_recent_engaged_sources(limit=12)]
        scored: list[tuple[float, dict]] = []
        for candidate in pool:
            source_text = self._normalized_post(str(candidate.get("source_text", "")))
            if not source_text:
                continue
            if self._source_already_used(candidate) or self._source_already_engaged(candidate):
                continue
            if not self._candidate_passes_comment_quality(candidate):
                continue
            novelty_penalty = 0.0
            for prior in recent_replies:
                if source_text[:80] and source_text[:80] in prior:
                    novelty_penalty += 20.0
            score = self._engagement_score(candidate) - novelty_penalty
            scored.append((score, dict(candidate)))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored]

    def _fallback_engagement_comment(self, candidate: dict) -> str:
        import random
        topic = str(candidate.get("topic", "")).strip().lower()
        hook = " ".join(str(candidate.get("hook", "")).split()).strip()
        source_text = " ".join(str(candidate.get("source_text", "")).split()).strip()
        metrics = self._candidate_metrics(candidate)
        basis = hook or source_text
        keywords = [
            word
            for word in re.findall(r"[A-Za-z][A-Za-z0-9$%.-]{3,}", basis)
            if word.lower() not in {"this", "that", "with", "from", "they", "have", "will", "about", "there"}
        ][:3]
        anchor = ", ".join(keywords) if keywords else (topic or "this move")
        if metrics.get("views", 0) >= 250000 or metrics.get("likes", 0) >= 2500:
            templates = [
                "The interesting part is {anchor}. Is the market reacting to the headline, or to the second-order effect?",
                "{anchor} feels like the real tell here. What breaks first if this keeps compounding?",
                "Everyone sees the headline, but {anchor} is the pressure point. What is the cleaner read?",
            ]
        elif any(t in topic for t in ("crypto", "bitcoin", "market", "trade", "macro", "economy", "rates")):
            templates = [
                "{anchor} is the part worth watching. Is this a flow signal or just positioning noise?",
                "This gets more interesting around {anchor}. What is the trade people are overcrowding?",
                "If {anchor} keeps moving, the obvious take may be the wrong one. What is mispriced?",
            ]
        else:
            templates = [
                "{anchor} is the useful signal here. What assumption is everyone making too quickly?",
                "The underrated angle is {anchor}. What changes if that is the actual driver?",
                "This is less about the headline and more about {anchor}. What is the next-order impact?",
            ]
        return self._public_safe_text(random.choice(templates).format(anchor=anchor), limit=220)
        
        openings = ["Honestly,", "Literally", "Actually", "Genuinely", "Just realized", "Thinking about"]
        observations = ["this completely shifts the perspective.", "the composition here is next level.", "this is exactly what the timeline needed.", "the aesthetic is unmatched.", "the energy here is flawless."]
        reactions = ["Obsessed.", "Beautiful.", "Iconic.", "Incredible.", "Wild."]
        emoji = random.choice(["✨", "🤌", "🔥", "💭", "🤍", "👀", "🎯", "👏", "⚡"])
        
        base = f"{random.choice(openings)} {random.choice(observations)} {random.choice(reactions)} {emoji}"
        

        return base
    def _safe_author_handle(self, candidate: dict) -> str:
        handle = str(candidate.get("author_handle", "")).strip()
        if not re.fullmatch(r"@[A-Za-z0-9_]{1,15}", handle):
            return ""
        return handle

    def _maybe_address_author(self, reply: str, candidate: dict) -> str:
        handle = self._safe_author_handle(candidate)
        if not handle or handle.lower() in reply.lower():
            return reply
        if len(f"{handle} {reply}") <= 220:
            return f"{handle} {reply}"
        return reply

    def _limit_reply_mentions(self, reply: str, candidate: dict) -> str:
        allowed = self._safe_author_handle(candidate).lower()
        seen_allowed = False

        def replace(match: re.Match) -> str:
            nonlocal seen_allowed
            handle = match.group(0)
            if allowed and handle.lower() == allowed and not seen_allowed:
                seen_allowed = True
                return handle
            return ""

        cleaned = re.sub(r"@[A-Za-z0-9_]{1,15}", replace, reply)
        return self._clean_generated_post(cleaned)

    def _ensure_engagement_question(self, reply: str, candidate: dict) -> str:
        return reply

    def _fallback_mention_reply(self, mention: dict) -> str:
        text = " ".join(str(mention.get("text", "")).split())
        keywords = [
            word
            for word in re.findall(r"[A-Za-z][A-Za-z0-9$%.-]{3,}", text)
            if word.lower() not in {"this", "that", "with", "from", "they", "have", "will", "about", "there", "what", "when"}
        ][:3]
        anchor = ", ".join(keywords) if keywords else "that point"
        options = [
            f"{anchor} is the part worth separating from the noise. The better read is usually where positioning has to adjust next.",
            f"The useful angle on {anchor}: follow who has to rebalance, not who has the loudest headline.",
            f"{anchor} only matters if it changes flows or incentives. Otherwise it is just timeline volatility.",
            f"The sharper question around {anchor} is whether it changes positioning, liquidity, or both.",
        ]
        for _ in range(len(options)):
            candidate = options[self.entropy.get_entropy_int(0, len(options) - 1)]
            safe = self._public_safe_text(candidate, limit=220)
            if safe and not self._looks_like_recent_reply_text(safe, limit=30):
                return safe
        return ""

    def _generate_engagement_comment(self, candidate: dict) -> str:
        source_text = str(candidate.get("source_text", "")).strip()
        if not source_text:
            return ""
        tier = self._candidate_comment_tier(candidate)
        thread_replies = self._reply_context_for_candidate(candidate, tier)
        prompt = PromptTemplates.trend_comment(
            source_text=source_text,
            topic=str(candidate.get("topic", "")).strip() or "general",
            metrics=self._candidate_metrics(candidate),
            author_handle=str(candidate.get("author_handle", "")).strip() or "unknown",
            recent_replies=self.memory.get_recent_engaged_sources(limit=3),
            thread_replies=thread_replies,
            tier=tier,
        )
        reply = self._clean_generated_post(self.llm.ask(prompt, timeout=120, role="creator"))
        if not reply:
            reply = self._clean_generated_post(self._ask_browser_llm(prompt) or "")
        if not reply:
            reply = self._fallback_engagement_comment(candidate)
        reply = self._public_safe_text(reply, limit=220)
        if not reply:
            reply = self._fallback_engagement_comment(candidate)
        reply = self._maybe_address_author(reply, candidate)
        reply = self._limit_reply_mentions(reply, candidate)
        reply = self._public_safe_text(reply, limit=220)
        if not reply or self._looks_like_recent_reply_text(reply, limit=30):
            reply = self._fallback_engagement_comment(candidate)
        return reply

    def _fallback_rephrase(self, candidate: dict) -> str:
        source_text = " ".join(str(candidate.get("source_text", "")).split())
        hook = str(candidate.get("hook", "")).strip()
        if hook:
            return _truncate(hook, 240)
        return _truncate(source_text, 240)

    def _rephrase_candidate(self, candidate: dict) -> str:
        source_text = str(candidate.get("source_text", "")).strip()
        if not source_text:
            return ""
        prompt = PromptTemplates.source_rewrite(
            source_text=source_text,
            topic=str(candidate.get("topic", "")).strip() or "general",
            metrics=self._candidate_metrics(candidate),
            recent_posts=self.memory.get_recent_posts(limit=6),
        )
        response = self._clean_generated_post(self._ask_browser_llm(prompt) or "")
        if not response:
            response = self._fallback_rephrase(candidate)
        safe = self._public_safe_text(response, limit=280)
        return safe or self._public_safe_text(self._fallback_rephrase(candidate), limit=280)

    def _prepare_candidate_media(self, candidate: dict) -> list[Path]:
        local_path = str(candidate.get("local_image_path", "")).strip()
        if local_path and Path(local_path).exists():
            return [Path(local_path)]
        media_type = self._candidate_media_type(candidate)
        media_url = self._candidate_media_url(candidate)
        video_url = str(candidate.get("video_url", "")).strip()
        thumbnail_url = str(candidate.get("thumbnail_url", "")).strip()
        source_url = str(candidate.get("source_url", "")).strip()
        topic_prefix = str(candidate.get("topic", "")).strip() or ("trend-video" if media_type == "video" else "trend-image")
        if not media_url:
            return []

        downloaded: Path | None = None
        if media_type == "video":
            if video_url.startswith("http"):
                downloaded = self.browser.download_media(video_url, prefix=topic_prefix)
            if not downloaded:
                log.warning("Video source had no downloadable video stream; skipping thumbnail-only repost for %s", source_url or media_url)
                return []
        else:
            downloaded = self.browser.download_media(media_url, prefix=topic_prefix)

        if downloaded:
            candidate["local_image_path"] = str(downloaded)
            self.memory.add_source_asset(
                topic=str(candidate.get("topic", "")).strip(),
                source_url=source_url,
                author_handle=str(candidate.get("author_handle", "")).strip(),
                source_text=str(candidate.get("source_text", "")).strip(),
                image_url=self._candidate_media_url(candidate),
                local_image_path=str(downloaded),
                score=float(candidate.get("score", 0.0) or 0.0),
                metadata={
                    "kind": "downloaded_source_video" if media_type == "video" else "downloaded_source_image",
                    "media_type": media_type,
                    "video_url": video_url,
                    "thumbnail_url": thumbnail_url,
                    "image_url": str(candidate.get("image_url", "")).strip(),
                    "metrics": candidate.get("metrics", {}) or {},
                },
            )
            return [downloaded]
        return []

    def generate_and_post(self) -> str:
        # Vanguard Pipeline
        # 1. Trend Collection (SignalHunter)
        trend_cards = self.signal_hunter.hunt_emerging_narratives({"keywords": []})
        
        # 2. Sentiment Analysis & 3. Strategic Planning (BrainPlanner)
        try:
            strategy = self.brain.think("Assessing overarching strategy for today's social media presence before posting.")
        except Exception as e:
            log.warning(f"BrainPlanner failed: {e}")
            strategy = "Aggressive alpha"
            
        # 4. Memory Review (MemoryVault)
        pending_predictions = self.memory_vault.review_predictions()
        
        ranked_candidates = self._candidate_rankings(trend_cards)
        candidate = None
        post = ""
        media_paths: list[Path] = []
        max_attempts = 3
        require_media = _env_enabled("poco_REQUIRE_MEDIA_FOR_X_POSTS", "1")
        
        for item in ranked_candidates[:max_attempts]:
            if item.get("simulated") and not (self.dry_run or _env_enabled("poco_ALLOW_SIMULATED_TRENDS", "0")):
                continue
                
            # 5. Content Generation
            candidate_post = self._rephrase_candidate(item)
            if not candidate_post:
                continue
            if self._looks_like_recent_post(candidate_post):
                continue
                
            # 6. Quality Filter (RiskMonitor & ReputationGuard)
            if not self.risk_monitor.check_risk(candidate_post):
                continue
            if not self.reputation_guard.validate(candidate_post):
                continue
                
            candidate_media = self._prepare_candidate_media(item)
            if require_media and not candidate_media:
                continue
                
            candidate = item
            post = candidate_post
            media_paths = candidate_media
            break

        if not candidate:
            log.warning("No candidate passed the Vanguard Quality Filters; skipping post.")
            self._trace_runtime("x_post", "no_candidate")
            return ""

        posted = False
        publish_enabled = _env_enabled("poco_ENABLE_X_POSTS", "1")
        self._trace_runtime(
            "post_generation",
            "ready",
            preview=post[:120],
            publish_enabled=publish_enabled,
            topic=candidate.get("topic", ""),
            media_type=self._candidate_media_type(candidate),
            has_media=bool(media_paths),
        )

        if self.dry_run or not publish_enabled:
            log.info("Trend source selected: %s", candidate.get("source_url", "") or candidate.get("author_handle", "unknown"))
            log.info("Drafted rephrased post: %s", post)
            self._trace_runtime("x_post", "draft_only", preview=post[:120], source=candidate.get("source_url", ""))
            posted = True
        else:
            # 7. Post
            if self._restore_site_session("twitter", reason="x_post"):
                self._record_posted_source(candidate, post)
                posted = self.browser.post_to_twitter(post, media_paths=media_paths)
            if not posted:
                self._trace_runtime("x_post", "unverified_after_attempt", reason="source marked used", source=candidate.get("source_url", ""))
            self._trace_runtime("x_post", "success" if posted else "failed", preview=post[:120], source=candidate.get("source_url", ""))

        self.last_posted_ok = posted
        self.session_posted_texts.add(post)
        
        # 8. Performance Review (InfluenceEngine via interactions tracking) & 9. Memory Update (MemoryVault)
        self.memory.add_memory(
            content=post,
            memory_type="post",
            importance=0.72,
            iteration=self.iteration,
            metadata={"posted": posted, "topic": candidate.get("topic", ""), "source_url": candidate.get("source_url", "")},
        )
        if (posted or self.dry_run or not publish_enabled) and not self._source_already_used(candidate):
            self.memory.add_performance(self.iteration, f"post-{int(time.time())}", post, 0, 0, 0)
            self._record_posted_source(candidate, post)
            
            # Periodically store predictions for continuity
            if "will" in post.lower() and len(post) > 50:
                self.memory_vault.store_prediction(post, 30)
                
        return post
    def _reset_public_comment_budget(self, reason: str) -> int:
        budget = max(0, _env_random_int("poco_COMMENTS_BETWEEN_POSTS_MIN", "poco_COMMENTS_BETWEEN_POSTS_MAX", 4, 8))
        self.public_comment_budget_remaining = budget
        self._trace_runtime("public_comment_budget", "reset", reason=reason, budget=budget)
        return budget

    def _comment_batch_size(self) -> int:
        return max(1, _env_random_int("poco_COMMENT_BATCH_MIN", "poco_COMMENT_BATCH_MAX", 1, 2))

    def public_image_comment_cycle(self, reason: str = "scheduled") -> dict:
        if self.public_comment_budget_remaining <= 0:
            self._trace_runtime("public_image_comments", "skipped", reason="budget_exhausted", trigger=reason)
            return {"commented": 0, "records": []}
        requested = min(self.public_comment_budget_remaining, self._comment_batch_size())
        self._trace_runtime(
            "public_image_comments",
            "start",
            trigger=reason,
            requested=requested,
            budget_remaining=self.public_comment_budget_remaining,
        )
        result = self.engage_with_trending_posts(max_comments_override=requested)
        commented = int(result.get("commented", 0) or 0)
        if commented > 0:
            self.public_comment_budget_remaining = max(0, self.public_comment_budget_remaining - commented)
        return result

    def run_initial_public_image_burst(self, reason: str = "post") -> None:
        min_cycles = max(0, _env_int("poco_INITIAL_COMMENT_BURST_CYCLES_MIN", 2))
        max_cycles = max(min_cycles, _env_int("poco_INITIAL_COMMENT_BURST_CYCLES_MAX", 5))
        cycles = random.randint(min_cycles, max_cycles) if max_cycles else 0
        for cycle in range(cycles):
            if self.public_comment_budget_remaining <= 0:
                break
            self.public_image_comment_cycle(reason=f"{reason}_burst")
            if not self.dry_run and cycle + 1 < cycles and self.public_comment_budget_remaining > 0:
                time.sleep(max(0, _env_random_int("poco_INITIAL_COMMENT_BURST_COOLDOWN_MIN_SECONDS", "poco_INITIAL_COMMENT_BURST_COOLDOWN_MAX_SECONDS", 15, 45)))

    def engage_with_trending_posts(self, max_comments_override: int | None = None) -> dict:
        import random; max_comments_override = max_comments_override or random.randint(10, 30)
        if not _env_enabled("poco_ENABLE_TREND_COMMENTS", "1"):
            return {"commented": 0, "cards": []}
        trend_cards = self.research_trends()
        candidates = self._engagement_candidates(trend_cards)
        max_comments_cap = max(1, _env_int("poco_MAX_TREND_COMMENTS_PER_CYCLE_CAP", 6))
        configured_max = max_comments_override if max_comments_override is not None else _env_int("poco_MAX_TREND_COMMENTS_PER_CYCLE", 2)
        max_comments = max(1, min(max_comments_cap, int(configured_max)))
        engaged = 0
        attempts = 0
        records: list[dict] = []
        for candidate in candidates:
            if attempts >= max_comments:
                break
            source_url = str(candidate.get("source_url", "")).strip()
            if not source_url:
                continue
            comment = self._generate_engagement_comment(candidate)
            if (
                not comment
                or self._looks_like_recent_post(comment, limit=20)
                or self._looks_like_recent_reply_text(comment, limit=30)
            ):
                continue
            attempts += 1
            publish_enabled = _env_enabled("poco_ENABLE_X_COMMENTS", "1")
            posted = False
            if self.dry_run or not publish_enabled:
                posted = True
                self._trace_runtime("trend_comment", "draft_only", preview=comment[:120], source=source_url)
            else:
                if self._restore_site_session("twitter", reason="trend_comment"):
                    posted = self.browser.reply_to_tweet(source_url, comment)
                if not posted:
                    self.recover_page_confusion(
                        goal="reply to the selected trending X post with the prepared engagement comment",
                        site="twitter",
                        error="trend comment action failed",
                    )
            self.memory.add_interaction(
                user_handle=str(candidate.get("author_handle", "")).strip() or "trend-engagement",
                user_comment=str(candidate.get("source_text", "")).strip(),
                my_reply=comment,
                topics=[str(candidate.get("topic", "")).strip()] if candidate.get("topic") else ["trend-engagement"],
            )
            if posted:
                engaged += 1
            if posted or (publish_enabled and not self.dry_run):
                self._record_source_engagement(candidate, comment)
            records.append(
                {
                    "source_url": source_url,
                    "author_handle": candidate.get("author_handle", ""),
                    "topic": candidate.get("topic", ""),
                    "comment": comment,
                    "posted": posted,
                }
            )
            if posted and not self.dry_run:
                time.sleep(max(8, _env_int("poco_COMMENT_COOLDOWN_SECONDS", 18)))
        self._trace_runtime("trend_comments", "complete", commented=engaged, attempted=attempts)
        return {"commented": engaged, "cards": trend_cards, "records": records}

    def check_mentions(self) -> int:
        if not _env_enabled("poco_ENABLE_X_REPLIES", "1"):
            return 0
        if not self._restore_site_session("twitter", reason="mentions"):
            return 0
        mentions = self.browser.get_mentions(limit=10)
        replies = 0
        for mention in mentions[:5]:
            mention_url = str(mention.get("url", "")).strip()
            if not mention.get("text") or not mention_url:
                continue
            if mention_url in self.session_replied_urls:
                continue
            if self._is_identity_bait(mention["text"]):
                continue
            prompt = PromptTemplates.reply_generation(
                comment=mention["text"],
                user_handle=mention.get("user", "unknown"),
                user_history=self.memory.get_user_history(mention.get("user", "unknown"), limit=2),
            )
            reply = self._public_safe_text(self.llm.ask(prompt, timeout=30, role="chat").strip(), limit=220)
            if not reply:
                reply = self._public_safe_text(self._ask_browser_llm(prompt) or "", limit=220)
            if not reply:
                reply = self._fallback_mention_reply(mention)
            if self._looks_like_recent_post(reply, limit=12) or self._looks_like_recent_reply_text(reply, limit=30):
                continue
            self.session_replied_urls.add(mention_url)
            if self.dry_run or self.browser.reply_to_tweet(mention_url, reply):
                self.memory.add_interaction(
                    user_handle=mention.get("user", "unknown"),
                    user_comment=mention["text"],
                    my_reply=reply,
                )
                replies += 1
        return replies

    def recover_page_confusion(self, goal: str, site: str = "", error: str = "") -> dict:
        if self.browser.driver is None:
            return {}
        if not self._ensure_browser_ready(f"page_confusion:{site or 'unknown'}"):
            return {}
        artifacts = self.browser.capture_page_artifacts(site or "page-confusion")
        html_excerpt = ""
        source_path = artifacts.get("source_path", "")
        if source_path and Path(source_path).exists():
            try:
                html_excerpt = Path(source_path).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                html_excerpt = ""
        current_url = str(artifacts.get("url", "") or "")
        site_key = site or self._site_from_url(current_url)
        known_selectors = self.memory.get_selector_candidates(site_key, goal, limit=6)
        for known in known_selectors:
            selector = str(known.get("selector", "")).strip()
            action = str(known.get("action", "click")).strip() or "click"
            if selector and self.browser.perform_selector_action(selector, action, timeout=12):
                record = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "goal": goal,
                    "site": site_key,
                    "error": error,
                    "url": current_url,
                    "selector_payload": known,
                    "executed": True,
                    "artifacts": artifacts,
                    "reused_selector": True,
                }
                return record
        prompt = PromptTemplates.selenium_stuck(html_excerpt, goal)
        raw = self._ask_browser_llm(prompt) or ""
        if not raw:
            raw = self.llm.ask(prompt, timeout=60, role="selector") or ""
        payload = self._extract_selector_payload(raw)
        selector = str(payload.get("selector", "")).strip()
        action = str(payload.get("action", "click")).strip() or "click"
        value = str(payload.get("value", "")).strip()
        reason = str(payload.get("reason", error or "selector recovery")).strip()

        executed = False
        if selector:
            executed = self.browser.perform_selector_action(selector, action, value=value, timeout=20)
            if executed:
                self.memory.remember_selector(
                    site=site_key,
                    goal=goal,
                    selector=selector,
                    action=action,
                    confidence=0.82,
                    notes=reason,
                )
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "goal": goal,
            "site": site_key,
            "error": error,
            "url": current_url,
            "selector_payload": payload,
            "executed": executed,
            "artifacts": artifacts,
        }
        return record

    def _extract_selector_payload(self, raw: str) -> dict:
        for candidate in _json_candidates(raw):
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

    def execute_task(self, task: str) -> None:
        plan = self.brain.think(task, "external task from task.txt")
        action = "RESEARCH"
        self.memory.add_memory(
            content=f"Task: {task}\nPlan: {plan}",
            memory_type="observation",
            importance=0.8,
            iteration=self.iteration,
        )
        if any(keyword in task.lower() for keyword in ("post", "tweet", "x.com")):
            action = "POST"
            self.generate_and_post()
        self._write_task_status(task, f"Completed with action {action}", action=action)
        (self.project_root / "task.txt").write_text("", encoding="utf-8")

    def weekly_reflection(self) -> None:
        prompt = PromptTemplates.weekly_reflection(
            top_posts=self.memory.get_top_performers(days=7, limit=10),
            current_beliefs=[item["text"] for item in self.memory.get_beliefs(limit=20, min_strength=0.0)],
        )
        raw = self.llm.ask(prompt, timeout=120, role="summary")
        if not raw:
            raw = self._ask_browser_llm(prompt) or ""
        if not raw:
            return
        try:
            reflection = json.loads(raw)
        except Exception:
            reflection = {"themes": [], "new_beliefs": [], "refinements": [], "strategy": raw[:300]}
        for belief in reflection.get("new_beliefs", []):
            self.memory.add_belief(belief, strength=0.55, iteration=self.iteration)
        self.memory.add_reflection(
            week_start=datetime.utcnow().strftime("%Y-%m-%d"),
            reflection_text=json.dumps(reflection),
            new_beliefs=reflection.get("new_beliefs", []),
        )
        self.memory.weaken_beliefs()

    def _next_repo_name(self, next_iteration: int) -> str:
        template = os.environ.get("poco_REPO_TEMPLATE", "v{iteration}").strip() or "v{iteration}"
        try:
            candidate = template.format(iteration=next_iteration, current_repo=self.current_repo, current=self.current_repo)
        except Exception:
            candidate = f"v{next_iteration}"
        candidate = candidate.strip().replace(" ", "-")
        if not candidate or candidate == self.current_repo:
            return f"v{next_iteration}"
        return candidate

    def _max_iteration(self) -> int:
        raw = os.environ.get("poco_MAX_ITERATION", "0").strip()
        try:
            return max(0, int(raw))
        except Exception:
            return 0

    def _secrets_payload(self) -> dict[str, str]:
        return {
            "GH_PAT": self.accounts.github_token,
            "GH_PAT_FG": self.accounts.github_token_fg,
            "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "").strip(),
            "poco_X_USERNAME": self.accounts.twitter_username,
            "poco_X_PASSWORD": self.accounts.twitter_password,
            "poco_X_DM_PASSCODE": self.accounts.twitter_dm_passcode,
            "poco_GOOGLE_EMAIL": self.accounts.google_email,
            "poco_GOOGLE_PASSWORD": self.accounts.google_password,
            "poco_PROTON_USERNAME": self.accounts.proton_username,
            "poco_PROTON_PASSWORD": self.accounts.proton_password,
            "poco_CHATGPT_EMAIL": self.accounts.chatgpt_email,
            "poco_CHATGPT_PASSWORD": self.accounts.chatgpt_password,
            "poco_DEEPSEEK_EMAIL": self.accounts.deepseek_email,
            "poco_DEEPSEEK_PASSWORD": self.accounts.deepseek_password,
        }

    def _logic_only_cycle(self) -> dict:
        self._trace_runtime("github_loop_only", "start")
        self.cleanup_previous_birth()
        max_iteration = self._max_iteration()
        if max_iteration and self.iteration >= max_iteration:
            result = {
                "mode": "github_loop_only",
                "iteration": self.iteration,
                "current_repo": self.current_repo,
                "stopped_at_max": True,
                "max_iteration": max_iteration,
            }
            self.memory.close()
            return result
        wait_seconds = float(os.environ.get("poco_LOOP_WAIT_SECONDS", "5") or "5")
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        result = self.prepare_for_rebirth()
        self._save_iteration(result["next_iteration"])
        self.memory.close()
        self._complete_rebirth(result)
        return result

    def prepare_for_rebirth(self) -> dict:
        snapshot_dir = self.data_dir / "snapshots" / f"iter_{self.iteration}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        beliefs = self.memory.get_beliefs(limit=50, min_strength=0.0)
        (snapshot_dir / "beliefs.txt").write_text(
            "\n".join(f"{item['text']} ({item['strength']:.2f})" for item in beliefs),
            encoding="utf-8",
        )
        memory_db = self.data_dir / "poco_memory.db"
        if memory_db.exists():
            shutil.copy2(memory_db, snapshot_dir / memory_db.name)
        stats = self.memory.get_stats()
        next_iteration = self.iteration + 1
        next_repo = self._next_repo_name(next_iteration)
        private_repo = _env_enabled("poco_REPO_PRIVATE", "0")
        self.memory.record_lineage(
            iteration=self.iteration,
            repo_name=self.current_repo,
            repo_url=self.current_url,
            snapshot_path=str(snapshot_dir),
            notes=f"Prepared in final-puss on iteration {self.iteration}",
        )
        try:
            pass
        except Exception:
            pass
        rebirth = {
            "next_iteration": next_iteration,
            "new_repo_name": next_repo,
            "new_repo_url": f"https://github.com/{self.accounts.github_username}/{next_repo}",
            "current_repo": self.current_repo,
            "snapshot_path": str(snapshot_dir),
            "belief_count": len(beliefs),
            "memory_stats": stats,
            "codex_purpose": self.codex._who(),
            "ancestor_repo": self.current_repo,
            "private_repo": private_repo,
        }
        (snapshot_dir / "rebirth_manifest.json").write_text(json.dumps(rebirth, indent=2), encoding="utf-8")
        (self.project_root / "rebirth_data.json").write_text(json.dumps(rebirth, indent=2), encoding="utf-8")
        self._prune_old_snapshots()
        return rebirth

    def _send_rebirth_email(self, rebirth_data: dict) -> None:
        if self.dry_run:
            return
        if not self.accounts.proton_username or not self.accounts.proton_password or not self.accounts.google_email:
            return
        top_beliefs = self.memory.get_beliefs(limit=1, min_strength=0.0)
        top_belief = top_beliefs[0]["text"] if top_beliefs else "unknown"
        subject = f"[NEXUS] Iteration {rebirth_data['next_iteration']} Awakening"
        body = PromptTemplates.rebirth_email_summary(
            iteration=rebirth_data["next_iteration"],
            new_repo=rebirth_data["new_repo_name"],
            beliefs_count=rebirth_data["belief_count"],
            post_count=len(self.memory.get_recent_posts(limit=100)),
            top_belief=top_belief,
        )
        browser_was_running = self.browser.driver is not None
        try:
            if not browser_was_running:
                self.browser.start()
            self.browser.send_email_protonmail(
                self.accounts.proton_username,
                self.accounts.proton_password,
                to=self.accounts.google_email,
                subject=subject,
                body=body,
            )
        finally:
            if not browser_was_running:
                self.browser.stop()

    def _complete_rebirth(self, rebirth_data: dict) -> None:
        if self.dry_run:
            return
        if not self.accounts.github_username or not self.accounts.github_token:
            log.warning("Skipping rebirth push because GitHub credentials/token are missing")
            return
        repo_name = rebirth_data["new_repo_name"]
        private_repo = bool(rebirth_data.get("private_repo"))
        try:
            created = self.github.create_repo(
                repo_name=repo_name,
                description=f"Final Puss Poco iteration {rebirth_data['next_iteration']}",
                private=private_repo,
            )
            log.info("Repo ready: %s", created.get("html_url", repo_name))
            profile_dir = None if _env_enabled("poco_GITHUB_LOOP_ONLY", "0") else self.profile_dir
            self.github.push_project_snapshot(
                project_root=self.project_root,
                repo_name=repo_name,
                commit_message=f"Birth v{rebirth_data['next_iteration']} from {self.current_repo}",
                next_iteration=rebirth_data["next_iteration"],
                current_repo=self.current_repo,
                profile_dir=profile_dir,
                persistent_data_dir=self.data_dir,
            )
            self.github.sync_actions_secrets(repo_name, self._secrets_payload())
            if _env_enabled("poco_TRIGGER_AFTER_PUSH", "0"):
                triggered = False
                try:
                    triggered = self.github.trigger_workflow(repo_name)
                except Exception as trigger_exc:
                    log.warning("Workflow trigger failed, trying repository dispatch: %s", trigger_exc)
                if not triggered:
                    self.github.repository_dispatch(repo_name)
        except Exception as exc:
            log.error("Autonomous rebirth failed: %s", exc)
            raise RuntimeError(f"Autonomous rebirth failed: {exc}") from exc

    def run_forever(self, hours_per_run: float = 5.25) -> dict:
        run_started_at = time.time()
        def _hard_deadend():
            log.error("HARD DEADLINE REACHED! Forcing shutdown to give organism extra time!")
            import os
            os._exit(1)
            
        import threading
        deadend_timer = threading.Timer(hours_per_run * 3600, _hard_deadend)
        deadend_timer.daemon = True
        deadend_timer.start()

        max_runtime_raw = os.environ.get("poco_MAX_RUNTIME_HOURS", "").strip()
        effective_hours = hours_per_run
        if max_runtime_raw:
            try:
                effective_hours = min(hours_per_run, max(0.1, float(max_runtime_raw)))
            except Exception:
                effective_hours = hours_per_run
        elif _env_enabled("GITHUB_ACTIONS", "0"):
            effective_hours = min(hours_per_run, 5.0)
        log.info(
            "Starting iteration %s | profile=%s | requested_hours=%s | effective_hours=%s",
            self.iteration,
            self.profile_dir,
            hours_per_run,
            effective_hours,
        )
        self._trace_runtime("run", "start", hours_per_run=hours_per_run, effective_hours=effective_hours, profile=str(self.profile_dir))
        shutdown_margin = max(300, _env_int("poco_SHUTDOWN_MARGIN_SECONDS", 2400))
        end_at = run_started_at + (effective_hours * 3600)
        action_end_at = max(run_started_at, end_at - shutdown_margin)
        if _env_enabled("poco_GITHUB_LOOP_ONLY", "0"):
            return self._logic_only_cycle()
        if not self.dry_run:
            self._trace_runtime("browser_start", "start")
            self.browser.start()
            self._trace_runtime("browser_start", "success")
            self.cleanup_previous_birth()
            self._trace_runtime("browser_warmup", "start")
            self.browser.warmup()
            self._trace_runtime("browser_warmup", "success")
            
            # Use identical self-healing session restoration at boot
            twitter_ok = self._restore_site_session("twitter", reason="startup")
            self._trace_runtime("x_login", "success" if twitter_ok else "failed")
            if not twitter_ok and self.accounts.twitter_username and self.accounts.twitter_password:
                self.recover_page_confusion("log into X and reach the home timeline", site="twitter", error="x login failed")

            github_ok = self._restore_site_session("github", reason="startup")
            self._trace_runtime("github_login", "success" if github_ok else "failed")
            if not github_ok and self.accounts.github_username and self.accounts.github_password:
                self.recover_page_confusion("log into GitHub and reach the account dashboard", site="github", error="github login failed")

            self.gemini_available = self._restore_site_session("gemini", reason="startup")
            self._trace_runtime("gemini_login", "success" if self.gemini_available else "failed")

            self.chatgpt_available = self._restore_site_session("chatgpt", reason="startup")
            self._trace_runtime("chatgpt_login", "success" if self.chatgpt_available else "failed")

            self.deepseek_available = self._restore_site_session("deepseek", reason="startup")
            self._trace_runtime("deepseek_login", "success" if self.deepseek_available else "failed")
            if not self.deepseek_available and self.accounts.deepseek_email and self.accounts.deepseek_password:
                self.recover_page_confusion("open DeepSeek chat and make it ready for selector recovery", site="deepseek", error="deepseek login failed")

        task = self._read_task_txt()
        if task:
            self.execute_task(task)
        else:
            self._write_task_status("", "", "NONE")

        schedule.clear()
        schedule.every().sunday.at("23:00").do(self.weekly_reflection)
        
        post_min = 10
        post_max = 140
        comment_min = 3
        comment_max = max(comment_min, _env_int("poco_COMMENT_INTERVAL_MAX_MINUTES", 8))
        mention_min = 1
        mention_max = max(mention_min, _env_int("poco_MENTION_INTERVAL_MAX_MINUTES", 5))
        
        now = time.time()
        next_post_at = now + (_env_random_int("poco_POST_INTERVAL_MIN_MINUTES", "poco_POST_INTERVAL_MAX_MINUTES", 60, 120) * 60)
        next_comment_at = now + (_env_random_int("poco_COMMENT_INTERVAL_MIN_MINUTES", "poco_COMMENT_INTERVAL_MAX_MINUTES", 15, 30) * 60)
        next_mention_at = now + (_env_random_int("poco_MENTION_INTERVAL_MIN_MINUTES", "poco_MENTION_INTERVAL_MAX_MINUTES", mention_min, mention_max) * 60)
        
        self._trace_runtime(
            "schedule",
            "ready",
            post_window_minutes=[post_min, post_max],
            comment_window_minutes=[comment_min, comment_max],
            next_post_seconds=int(next_post_at - now),
            next_comment_seconds=int(next_comment_at - now),
        )

        first_post = self.generate_and_post()
        self._reset_public_comment_budget("initial_post")
        self.run_initial_public_image_burst("initial_post")
        
        if _env_enabled("poco_BOOT_SEQUENCE_ONLY", "0"):
            if not self.last_posted_ok:
                raise RuntimeError("X post failed during boot validation")
            self._trace_runtime("boot_sequence", "complete", first_post=first_post[:120])
            if not self.dry_run:
                self.browser.stop()
            self.memory.close()
            return {"mode": "boot_validation", "iteration": self.iteration, "current_repo": self.current_repo, "first_post": first_post, "x_posted": self.last_posted_ok}
        
        self._trace_runtime("schedule", "deadline_ready", shutdown_margin_seconds=shutdown_margin)
        
        # Setup global OS-level watchdog for hung sockets
        import platform
        if platform.system() != "Windows":
            try:
                import signal
                def _watchdog_handler(signum, frame):
                    raise TimeoutError("WATCHDOG TIMEOUT: Cycle hung for > 30 minutes! Forcing cycle abort.")
                if hasattr(signal, "SIGALRM"):
                    signal.signal(signal.SIGALRM, _watchdog_handler)
            except Exception:
                pass

        while time.time() < action_end_at:
            try:
                if platform.system() != "Windows":
                    import signal
                    if hasattr(signal, "alarm"):
                        signal.alarm(1800)  # 30 minute absolute hard limit per cycle
                schedule.run_pending()
                now = time.time()
                if now >= next_post_at:
                    self.generate_and_post()
                    self._reset_public_comment_budget("scheduled_post")
                    self.run_initial_public_image_burst("scheduled_post")
                    now = time.time()
                    next_post_at = now + (_env_random_int("poco_POST_INTERVAL_MIN_MINUTES", "poco_POST_INTERVAL_MAX_MINUTES", 60, 120) * 60)
                    next_comment_at = now + (_env_random_int("poco_COMMENT_INTERVAL_MIN_MINUTES", "poco_COMMENT_INTERVAL_MAX_MINUTES", 15, 30) * 60)
                if now >= next_comment_at:
                    self.public_image_comment_cycle(reason="scheduled")
                    now = time.time()
                    next_comment_at = now + (_env_random_int("poco_COMMENT_INTERVAL_MIN_MINUTES", "poco_COMMENT_INTERVAL_MAX_MINUTES", 15, 30) * 60)
                if now >= next_mention_at:
                    self.check_mentions()
                    now = time.time()
                    next_mention_at = now + (_env_random_int("poco_MENTION_INTERVAL_MIN_MINUTES", "poco_MENTION_INTERVAL_MAX_MINUTES", mention_min, mention_max) * 60)
            except Exception as exc:
                self.self_healer.record_failure(exc, "schedule.run_pending() failure")
            finally:
                if platform.system() != "Windows":
                    try:
                        import signal
                        if hasattr(signal, "alarm"):
                            signal.alarm(0)
                    except Exception:
                        pass
            next_due = min(next_post_at, next_comment_at, next_mention_at, action_end_at)
            sleep_seconds = 5 if self.dry_run else max(5, min(60, int(next_due - time.time())))
            time.sleep(sleep_seconds)
            if self.dry_run:
                break
        self._trace_runtime("schedule", "shutdown_margin_entered", seconds_left=max(0, int(end_at - time.time())))

        try:
            self.weekly_reflection()
        finally:
            if not self.dry_run:
                self.browser.stop()

        result = self.prepare_for_rebirth()
        self._save_iteration(result["next_iteration"])
        self._send_rebirth_email(result)
        self.memory.close()
        self._complete_rebirth(result)
        return result
