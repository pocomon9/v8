"""
NEXUS-PRIME-Ω  Self-Healing Engine  v2
========================================
When PocoPrime hits any error, this module:
  1. Captures the full traceback + relevant source file
  2. Asks its LOCAL brain (Ollama/tinyllama) for a fix
  3. If Ollama fails → opens a FRESH browser → asks ChatGPT
  4. If ChatGPT fails → tries DeepSeek
  5. Validates the fix (ast.parse), applies it, restarts
  6. UNLIMITED retries — PocoPrime NEVER gives up

Also provides think() — step-by-step LLM reasoning for the entity.
"""

from __future__ import annotations

import os
import re
import sys
import ast
import json
import time
import logging
import traceback
import subprocess
from pathlib import Path
from datetime import datetime

log = logging.getLogger("Poco-SelfHeal")

# --------------------------------------------------------------------------- #
#  LLM prompt builder — short and focused                                      #
# --------------------------------------------------------------------------- #

def _build_prompt(error_msg: str, tb: str, file_path: str, file_src: str) -> str:
    # Only send the relevant portion — the 60 lines around the error
    lines = file_src.split("\n")
    err_line = 0
    m = re.search(r'line (\d+)', tb)
    if m:
        err_line = max(0, int(m.group(1)) - 30)
    snippet = "\n".join(lines[err_line:err_line + 60])
    return (
        f"Fix this Python bug. Return ONLY the corrected full file.\n"
        f"ERROR: {error_msg}\n"
        f"FILE: {file_path}\n"
        f"SNIPPET:\n```python\n{snippet}\n```\n"
        f"Rules: valid Python only, no explanations, complete file."
    )

def _build_step_prompt(situation: str, context: str = "") -> str:
    return (
        f"You are PocoPrime, an autonomous AI agent.\n"
        f"Current situation: {situation}\n"
        f"Context: {context}\n"
        f"What is the exact next action to take? Be specific and brief (1-3 sentences)."
    )

# --------------------------------------------------------------------------- #
#  Strategy 1: Ollama (local LLM — fastest, no internet needed)                #
# --------------------------------------------------------------------------- #

def _ask_ollama(prompt: str, model: str = "tinyllama", timeout: int = 90) -> str:
    return ""
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=timeout
        )
        out = result.stdout.strip()
        if out:
            log.info(f"Ollama responded ({len(out)} chars)")
            return out
    except Exception as e:
        log.warning(f"Ollama unavailable: {e}")
    return ""

# --------------------------------------------------------------------------- #
#  Browser starter — standalone (no existing entity needed)                    #
# --------------------------------------------------------------------------- #

def _start_headless_browser():
    """Start a minimal headless Chrome for LLM queries."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1366,768")
        # Use Chromium on Linux (GitHub Actions)
        for cb in ["/usr/bin/chromium-browser", "/usr/bin/chromium",
                   "/usr/bin/google-chrome", "chromium-browser"]:
            try:
                opts.binary_location = cb
                d = webdriver.Chrome(options=opts)
                log.info(f"Standalone browser started: {cb}")
                return d
            except Exception:
                continue
    except Exception as e:
        log.warning(f"Could not start standalone browser: {e}")
    return None

# --------------------------------------------------------------------------- #
#  Strategy 2 & 3: ChatGPT / DeepSeek via browser                             #
# --------------------------------------------------------------------------- #

def _ask_llm_browser(prompt: str, driver, url: str,
                      input_sel: str, output_sel: str,
                      wait_sec: int = 35, site: str = "") -> str:
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys

        driver.get(url)
        time.sleep(8)

        inp = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, input_sel)))
        inp.click()
        # Type in chunks
        for chunk in [prompt[i:i+400] for i in range(0, len(prompt), 400)]:
            inp.send_keys(chunk)
            time.sleep(0.2)
        inp.send_keys(Keys.RETURN)
        time.sleep(wait_sec)

        resps = driver.find_elements(By.CSS_SELECTOR, output_sel)
        if resps:
            text = resps[-1].text.strip()
            log.info(f"{site} responded ({len(text)} chars)")
            return text
    except Exception as e:
        log.warning(f"{site} browser failed: {e}")
    return ""



def _login_chatgpt(driver) -> bool:
    """Login to ChatGPT before querying."""
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:
            from src.logins import Accounts
        except ImportError:
            from logins import Accounts
        driver.get("https://chatgpt.com/auth/login")
        time.sleep(5)
        # Click Log in
        try:
            btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//button[contains(.,'Log in') or contains(.,'Sign in')]")))
            btn.click()
            time.sleep(3)
        except Exception:
            pass
        # Email
        try:
            inp = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='email'],input[name='email'],input[type='text']")))
            inp.clear()
            inp.send_keys(Accounts.CHATGPT_EMAIL)
            time.sleep(1)
            for sel in ["button[type='submit']", "button"]:
                try:
                    driver.find_element(By.CSS_SELECTOR, sel).click()
                    break
                except Exception:
                    pass
            time.sleep(3)
        except Exception:
            pass
        # Password
        try:
            pw = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='password']")))
            pw.clear()
            pw.send_keys(Accounts.CHATGPT_PASSWORD)
            time.sleep(1)
            for sel in ["button[type='submit']", "button"]:
                try:
                    driver.find_element(By.CSS_SELECTOR, sel).click()
                    break
                except Exception:
                    pass
            time.sleep(7)
        except Exception:
            pass
        log.info("ChatGPT login attempted")
        return True
    except Exception as e:
        log.warning(f"ChatGPT login failed: {e}")
        return False


def _login_deepseek(driver) -> bool:
    """Login to DeepSeek before querying."""
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:
            from src.logins import Accounts
        except ImportError:
            from logins import Accounts
        driver.get("https://chat.deepseek.com/sign_in")
        time.sleep(5)
        try:
            inp = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "input[type='email'],input[placeholder*='mail'],input[type='text']")))
            inp.clear()
            inp.send_keys(Accounts.DEEPSEEK_EMAIL)
            time.sleep(1)
            pw = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            pw.clear()
            pw.send_keys(Accounts.DEEPSEEK_PASSWORD)
            time.sleep(1)
            for sel in ["button[type='submit']", "button"]:
                try:
                    driver.find_element(By.CSS_SELECTOR, sel).click()
                    break
                except Exception:
                    pass
            time.sleep(7)
        except Exception:
            pass
        log.info("DeepSeek login attempted")
        return True
    except Exception as e:
        log.warning(f"DeepSeek login failed: {e}")
        return False

def _ask_chatgpt_browser(prompt: str, driver) -> str:
    # Auto-login if not on ChatGPT already
    try:
        if "chatgpt.com" not in driver.current_url:
            _login_chatgpt(driver)
    except Exception:
        pass
    return _ask_llm_browser(
        prompt, driver,
        url="https://chatgpt.com/",
        input_sel="textarea, div[contenteditable='true']",
        output_sel="div.markdown, div[data-message-author-role='assistant']",
        wait_sec=35, site="ChatGPT"
    )


def _ask_gemini_browser(prompt: str, driver) -> str:
    return _ask_llm_browser(
        prompt, driver,
        url="https://gemini.google.com/app",
        input_sel="div[contenteditable='true'], textarea, rich-textarea",
        output_sel="message-content, div.model-response-text",
        wait_sec=35, site="Gemini"
    )

def _ask_deepseek_browser(prompt: str, driver) -> str:
    return _ask_llm_browser(
        prompt, driver,
        url="https://chat.deepseek.com/",
        input_sel="textarea, div[contenteditable='true']",
        output_sel="div.ds-markdown, div[class*='message']",
        wait_sec=40, site="DeepSeek"
    )

# --------------------------------------------------------------------------- #
#  Code extractor                                                               #
# --------------------------------------------------------------------------- #

def _extract_code(llm_response: str) -> str:
    m = re.search(r"```python\s*(.*?)```", llm_response, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)```", llm_response, re.DOTALL)
    if m:
        return m.group(1).strip()
    if "def " in llm_response or "import " in llm_response:
        return llm_response.strip()
    return ""

# --------------------------------------------------------------------------- #
#  Apply fix: validate + write with backup                                      #
# --------------------------------------------------------------------------- #

def _apply_fix(file_path: str, fixed_code: str) -> bool:
    try:
        ast.parse(fixed_code)
    except SyntaxError as e:
        log.error(f"LLM fix has syntax error: {e} — not applying")
        return False
    backup = file_path + f".bak{int(time.time())}"
    Path(backup).write_text(Path(file_path).read_text(encoding="utf-8"), encoding="utf-8")
    Path(file_path).write_text(fixed_code, encoding="utf-8")
    log.info(f"Fix applied: {file_path} (backup: {backup})")
    return True

# --------------------------------------------------------------------------- #
#  think() — step-by-step LLM reasoning for PocoPrime                        #
# --------------------------------------------------------------------------- #

def think(situation: str, context: str = "",
          driver=None, model: str = "tinyllama") -> str:
    """
    Ask the LLM what to do next given the current situation.
    PocoPrime calls this when stuck or before key actions.

    Returns a plain-English action description.
    """
    prompt = _build_step_prompt(situation, context)
    log.info(f"Thinking: {situation[:80]}...")

    # Try Ollama first
    resp = _ask_ollama(prompt, model=model, timeout=45)
    if resp:
        return resp.strip()

    # Try browser LLMs
    own_browser = False
    if driver is None:
        driver = _start_headless_browser()
        own_browser = True

    if driver:
        try:
            resp = _ask_chatgpt_browser(prompt, driver)
            if not resp:
                resp = _ask_deepseek_browser(prompt, driver)
        finally:
            if own_browser:
                try:
                    driver.quit()
                except Exception:
                    pass

    return resp.strip() if resp else "Continue with current plan."

# --------------------------------------------------------------------------- #
#  Main SelfHealer class                                                        #
# --------------------------------------------------------------------------- #

class SelfHealer:
    """
    PocoPrime's self-repair module.

    Unlimited retries — PocoPrime NEVER gives up.
    Each heal attempt tries: Brain → Ollama → ChatGPT → DeepSeek.
    Brain (BrainPlanner) is always asked FIRST — it reasons about the error
    using the same local Ollama pipeline. Only if brain fails does it
    escalate to direct Ollama, then browser-based ChatGPT/DeepSeek.

    Usage:
        healer = SelfHealer(driver=browser.driver, model='tinyllama')
        healer.heal(exception, traceback_str)
    """

    def __init__(self, driver=None, model: str = "tinyllama"):
        self.driver = driver
        self.model  = model
        self.heal_log = Path("data/self_heal_log.jsonl")
        self.heal_log.parent.mkdir(parents=True, exist_ok=True)
        self._attempt = 0

    def _log_event(self, event: dict):
        try:
            with open(self.heal_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({**event, "ts": datetime.utcnow().isoformat()}) + "\n")
        except Exception:
            pass

    def record_failure(self, exc: Exception, traceback_text: str) -> None:
        self._log_event({"status": "failure", "error": f"{type(exc).__name__}: {exc}", "context": traceback_text})

    def heal(self, exc: Exception, tb_str: str = "") -> bool:
        """
        Main heal method. Returns True if fix was applied.
        UNLIMITED attempts — tries forever until it finds a fix.
        """
        if not tb_str:
            tb_str = traceback.format_exc()
            
        exc_str = str(exc).lower()
        if 'timed out receiving message from renderer' in exc_str or 'page crash' in exc_str or 'stale element reference' in exc_str:
            log.warning('Browser freeze/crash detected! Auto-restarting browser and process...')
            if self.driver:
                try: self.driver.quit()
                except: pass
            self._restart()
            return True

        self._attempt += 1
        log.info("=" * 55)
        log.info(f"SELF-HEAL #{self._attempt} — PocoPrime repairing itself")
        log.info(f"Error: {type(exc).__name__}: {exc}")
        log.info("=" * 55)

        file_path = self._extract_file_from_tb(tb_str)
        if not file_path or not Path(file_path).exists():
            log.error(f"Cannot locate broken file: {file_path}")
            return False

        file_src = Path(file_path).read_text(encoding="utf-8")
        error_msg = f"{type(exc).__name__}: {exc}"
        prompt = _build_prompt(error_msg, tb_str, file_path, file_src)

        fixed_code = ""

        # Strategy 0: Brain (BrainPlanner — reasons about the error, uses Ollama internally)
        log.info("Strategy 0: Brain (BrainPlanner)...")
        try:
            from src.brain_planner import BrainPlanner
            _brain = BrainPlanner(driver=self.driver)
            brain_fix = _brain.consult_on_error(
                exc, context=file_path, goal="Fix the Python syntax/runtime error"
            )
            if brain_fix and len(brain_fix.strip()) > 20:
                fixed_code = _extract_code(brain_fix)
                if fixed_code:
                    log.info("Brain provided a fix ✓")
        except Exception as _be:
            log.warning(f"Brain strategy failed: {_be}")

        # Strategy 1: Ollama direct (local — fallback if brain fails)
        if not fixed_code:
            log.info("Strategy 1: Ollama direct (local)...")
            raw = _ask_ollama(prompt, model=self.model)
            if raw:
                fixed_code = _extract_code(raw)

        # For browser strategies, use existing driver OR start a fresh one
        browser_driver = self.driver
        own_browser    = False
        if not fixed_code:
            if browser_driver is None:
                log.info("Starting standalone browser for LLM...")
                browser_driver = _start_headless_browser()
                own_browser = True


        # Strategy 2: Gemini browser
        if not fixed_code and browser_driver:
            log.info("Strategy 2: Gemini browser...")
            raw = _ask_gemini_browser(prompt, browser_driver)
            if raw:
                fixed_code = _extract_code(raw)

        # Strategy 3: ChatGPT browser
        if not fixed_code and browser_driver:
            log.info("Strategy 3: ChatGPT browser...")
            raw = _ask_chatgpt_browser(prompt, browser_driver)
            if raw:
                fixed_code = _extract_code(raw)

        # Strategy 4: DeepSeek browser
        if not fixed_code and browser_driver:
            log.info("Strategy 4: DeepSeek browser...")
            raw = _ask_deepseek_browser(prompt, browser_driver)
            if raw:
                fixed_code = _extract_code(raw)

        # Cleanup own browser
        if own_browser and browser_driver:
            try:
                browser_driver.quit()
            except Exception:
                pass

        if not fixed_code:
            log.error("All LLM strategies failed this attempt — will retry on next error")
            self._log_event({"status": "failed", "attempt": self._attempt,
                             "error": error_msg, "file": file_path})
            return False

        applied = _apply_fix(file_path, fixed_code)
        self._log_event({
            "status": "applied" if applied else "syntax_error",
            "attempt": self._attempt, "error": error_msg,
            "file": file_path, "fix_len": len(fixed_code)
        })

        if applied:
            log.info("Fix applied! Restarting PocoPrime...")
            self._restart()
        return applied

    def _extract_file_from_tb(self, tb_str: str) -> str:
        matches = re.findall(r'File "([^"]+\.py)", line', tb_str)
        our_files = [
            f for f in matches
            if "src/" in f or "poco_prime.py" in f
        ]
        if our_files:
            return our_files[-1]
        for f in reversed(matches):
            if "/python3" not in f and "/lib/" not in f:
                return f
        return ""

    def _restart(self):
        log.info(f"Restarting: {sys.executable} {' '.join(sys.argv)}")
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
