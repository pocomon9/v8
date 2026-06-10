"""
NEXUS-PRIME-Ω  Brain Planner v2
=================================
TRUE AI AGENT — acts exactly like a human:

  STARTUP:
    1. Check brain (LLM) is alive — fix if not
    ↓
  GOAL SET:
    2. Plan full step list
    ↓
  CONTINUOUS LOOP (forever until done):
    3. Do one action
    4. Read page → "where am I right now?"
    5. Ask brain → "what should I do next?"
    6. If error → ask brain: "I hit X error, how do I fix it?"
    7. Brain answer → try it → read again → ask again
    8. Never stop. Never skip. Always consult.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import shutil
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

log = logging.getLogger("Poco-Brain")


# ========================================================================= #
#  Ollama + Browser LLM callers                                              #
# ========================================================================= #

def _ollama(prompt: str, model: str = "tinyllama", timeout: int = 60) -> str:
    return ""
    """Try Ollama. Returns empty string if unavailable."""
    if not shutil.which("ollama"):
        return ""
    configured = os.environ.get("poco_OLLAMA_MODELS", "tinyllama,deepseek-coder:1.3b,phi3:mini")
    fallback_models = [item.strip() for item in configured.split(",") if item.strip()]
    for m in [model, *fallback_models]:
        try:
            r = subprocess.run(
                ["ollama", "run", m, prompt],
                capture_output=True, text=True, timeout=timeout
            )
            out = r.stdout.strip()
            if out:
                return out
        except Exception:
            continue
    return ""
_BROWSER_LLM_SELECTORS = {

    "chatgpt": {

        "input":  ["#prompt-textarea", "textarea[data-id]", "div[contenteditable=\'true\']", "textarea"],

        "output": ["div.markdown", "[data-message-author-role=\'assistant\'] p", ".prose"],

    },

    "deepseek": {

        "input":  ["#chat-input", "textarea.chat-input", "div[contenteditable=\'true\']", "textarea"],

        "output": ["div.ds-markdown", ".message-content", "[class*=\'assistant\'] p"],

    },

}





def _ask_browser_llm(prompt: str, driver, brain, url: str,

                     inp_sel: str, out_sel: str,

                     wait_sec: int = 30, site: str = "LLM") -> str:

    """Ask ChatGPT or DeepSeek via browser. Uses HARDCODED selectors only."""

    import time

    from selenium.webdriver.common.by import By

    from selenium.webdriver.support.ui import WebDriverWait

    from selenium.webdriver.support import expected_conditions as EC

    from selenium.webdriver.common.keys import Keys



    original_window = driver.current_window_handle

    try:

        driver.execute_script("window.open('');")

        driver.switch_to.window(driver.window_handles[-1])

        driver.get(url)

        time.sleep(8)



        site_key = "deepseek" if "deepseek" in url else "chatgpt"

        inp_sels = _BROWSER_LLM_SELECTORS[site_key]["input"]

        out_sels = _BROWSER_LLM_SELECTORS[site_key]["output"]



        inp = None

        for s in inp_sels:

            try:

                inp = WebDriverWait(driver, 8).until(

                    EC.element_to_be_clickable((By.CSS_SELECTOR, s)))

                break

            except Exception:

                continue

        if not inp:

            raise Exception(f"No input found on {site}")



        inp.click()

        time.sleep(0.5)

        for chunk in [prompt[i:i+300] for i in range(0, min(len(prompt), 1200), 300)]:

            inp.send_keys(chunk)

            time.sleep(0.1)

        inp.send_keys(Keys.RETURN)

        time.sleep(wait_sec)



        result = ""

        for s in out_sels:

            try:

                els = driver.find_elements(By.CSS_SELECTOR, s)

                if els:

                    result = els[-1].text.strip()

                    if result:

                        break

            except Exception:

                continue



        driver.close()

        driver.switch_to.window(original_window)

        return result



    except Exception as e:

        log.warning(f"{site} query failed: {e}")

        try:

            driver.close()

            driver.switch_to.window(original_window)

        except Exception:

            pass

        return ""









# ========================================================================= #



#  Step dataclass                                                             #



# ========================================================================= #







@dataclass



class Step:



    action: str



    done: bool = False



    result: str = ""



    attempts: int = 0











# ========================================================================= #



#  BrainPlanner v2                                                            #



# ========================================================================= #







class BrainPlanner:



    """



    PocoPrime's reasoning brain.







    Before anything: check brain is alive.



    For every action: act → read → think → act (infinite loop).



    For every error: consult brain first, always.



    """







    def __init__(self, driver=None, model: str = "tinyllama"):


        self.driver  = driver



        self.model   = model



        self.history: List[Dict] = []



        self.max_steps = 50



        self._brain_ok: Optional[bool] = None   # None = not checked yet



        # PocoPrime's identity — always injected into LLM context



        self._identity = (



            "I am pocomon9. "



            "Twitter: pocomon9 / NEXUSPRIME--1112. "



            "GitHub: pocomon9 / NEXUSPRIME--1112. "



            "Gmail: drpjfacts@gmail.com / D4P16R18J10. "



            "ProtonMail: nexusprime1112@proton.me / NEXUSPRIME--1112k. "



            "ChatGPT/DeepSeek: drpjfacts@gmail.com / D4P16R18J10k. "



        )







    # ------------------------------------------------------------------ #



    #  STEP 0: Brain health check — ALWAYS called first                   #



    # ------------------------------------------------------------------ #







    def brain_check(self) -> bool:



        """



        Verify LLM is reachable.



        Strategy:



          1. Try Ollama (local)



          2. Try starting Ollama service if not running



          3. Check driver available for browser LLMs



        Returns True if any LLM is usable.



        """



        if self._brain_ok is True:



            return True







        log.info("Brain health check...")







        # Try Ollama



        test = _ollama("ping", self.model, timeout=15)



        if test:



            log.info(f"Brain OK: Ollama ({self.model}) is live")



            self._brain_ok = True



            return True







        # Try to start Ollama service



        log.warning("Ollama not responding — trying to start service...")



        try:



            subprocess.Popen(["ollama", "serve"],



                             stdout=subprocess.DEVNULL,



                             stderr=subprocess.DEVNULL)



            time.sleep(10)



            test = _ollama("ping", "tinyllama", timeout=20)



            if test:



                self.model = "tinyllama"



                log.info("Brain OK: Ollama started, using tinyllama")



                self._brain_ok = True



                return True



        except Exception as e:



            log.warning(f"Could not start Ollama: {e}")







        # Check browser LLM fallback



        if self.driver:



            log.info("Ollama unavailable — browser LLMs (ChatGPT/DeepSeek) will be used")



            self._brain_ok = True   # browser available



            return True







        log.error("NO BRAIN AVAILABLE — all LLMs offline and no browser driver")



        self._brain_ok = False



        return False







    def ensure_brain(self):



        """Call before any important action. Blocks until brain is available."""



        retries = 0



        while not self.brain_check():



            retries += 1



            log.warning(f"Brain unavailable — waiting 30s (attempt {retries})...")



            time.sleep(30)



            self._brain_ok = None   # reset so next check re-tries







    def _query(self, prompt: str, timeout: int = 45) -> str:

        """

        Query LLM: Ollama FIRST (local brain).

        ONLY fall back to browser LLMs if Ollama returns nothing.

        Never call chain HTML from inside _ask_browser_llm (infinite loop!).

        """

        # 1. Ollama — primary brain always

        resp = _ollama(prompt, self.model, timeout=timeout)

        if resp:

            return resp



        # 2. Browser LLMs — only when Ollama is dead (no driver=brain to avoid recursion)

        if self.driver:

            log.info("Ollama empty — trying ChatGPT browser")

            resp = _ask_browser_llm(

                prompt, self.driver, brain=None,

                url="https://chatgpt.com/",

                inp_sel="#prompt-textarea",

                out_sel="div.markdown",

                wait_sec=30, site="ChatGPT"

            )

            if resp:

                return resp

            log.info("ChatGPT failed — trying DeepSeek browser")

            resp = _ask_browser_llm(

                prompt, self.driver, brain=None,

                url="https://chat.deepseek.com/",

                inp_sel="#chat-input",

                out_sel="div.ds-markdown",

                wait_sec=35, site="DeepSeek"

            )

            if resp:

                return resp



        return ""



    def read_page_state(self, include_html: bool = False) -> str:



        """Where am I right now? URL + title + visible text + optional full HTML."""



        if not self.driver:



            return "No browser"



        try:



            url   = self.driver.current_url



            title = self.driver.title



            body  = self.driver.find_element("tag name", "body").text[:800]



            state = f"URL: {url}\nTITLE: {title}\nVISIBLE_TEXT:\n{body}"



            if include_html:



                html = self.driver.page_source[:4000]



                state += f"\n\nFULL_HTML (first 4000 chars):\n{html}"



            return state



        except Exception as e:



            return f"Page read failed: {e}"







    # ------------------------------------------------------------------ #



    #  consult_on_error — EVERY error handler calls this                  #



    # ------------------------------------------------------------------ #







    def consult_on_error(self, error: Exception, context: str = "",



                         goal: str = "") -> str:



        """



        Ask brain: "I hit this error while doing X. How do I fix it?"



        Returns a plain-English action to try.







        Call from EVERY except block:



            solution = self.brain.consult_on_error(e, context="logging in to Twitter")



        """



        if not self.brain_check():



            return "Retry after waiting 10 seconds"







        page_state = self.read_page_state(include_html=True)  # full HTML for LLM



        prompt = (



            f"You are PocoPrime, an AI agent controlling a browser.\n"



            f"IDENTITY: {self._identity}\n"



            f"GOAL: {goal or 'unknown'}\n"



            f"CURRENT ACTION: {context}\n"



            f"ERROR ENCOUNTERED: {type(error).__name__}: {error}\n"



            f"CURRENT PAGE STATE (with full HTML):\n{page_state}\n\n"



            f"Using the HTML above and knowing my credentials, "



            f"what is the EXACT next action to fix this error?\n"



            f"Return ONE specific CSS selector, URL, or text to type. No explanation."



        )



        log.info(f"Brain consulting on error: {type(error).__name__}: {str(error)[:60]}")



        resp = self._query(prompt, timeout=45)



        solution = resp.strip() if resp else "Wait 5 seconds and retry"



        log.info(f"Brain says: {solution[:100]}")



        return solution







    # ------------------------------------------------------------------ #



    #  Planning                                                           #



    # ------------------------------------------------------------------ #











    def find_element_chain(self, html_source: str, goal: str, target_desc: str, chunk_size: int = 1500) -> str:



        """



        CHAIN HTML METHOD:



        Splits HTML into small chunks. Feeds to LLM one by one.



        LLM either replies with CSS selector if it finds the element, or 'NEXT' if not.



        """



        if not self.brain_check():



            return "body"  # dumb fallback







        # Clean HTML slightly to save tokens: remove scripts/svgs



        import re



        html = re.sub(r'<script.*?</script>', '', html_source, flags=re.IGNORECASE|re.DOTALL)



        html = re.sub(r'<svg.*?</svg>', '', html, flags=re.IGNORECASE|re.DOTALL)



        html = re.sub(r'<style.*?</style>', '', html, flags=re.IGNORECASE|re.DOTALL)



        



        chunks = [html[i:i+chunk_size] for i in range(0, len(html), chunk_size)]



        



        log.info(f"Chain HTML started: {len(chunks)} chunks to check for '{target_desc}'")



        



        for i, chunk in enumerate(chunks):



            prompt = (



                f"You are PocoPrime, a browser automation expert.\n"



                f"Goal: {goal}\n"



                f"Target to find: {target_desc}\n\n"



                f"I am sending you HTML chunk {i+1}/{len(chunks)}.\n"



                f"CHUNK:\n{chunk}\n\n"



                f"If you see the target element (like an input field, button, etc) in this chunk, "



                f"return ONLY its exact CSS Selector or XPath.\n"



                f"If the target is NOT in this chunk, return exactly: NEXT\n"



                f"Do not explain. Just the selector or NEXT."



            )



            



            resp = self._query(prompt, timeout=20)



            if not resp:



                continue



                



            # Clean response: take only first non-empty line (LLM may return multiline invalid selectors)

            resp = resp.strip().replace('`', '').replace('"', '').replace("'", "")

            resp = next((ln.strip() for ln in resp.splitlines() if ln.strip()), "").strip()

            



            if resp.upper() == "NEXT" or "NEXT" in resp.upper():



                log.info(f"Chain {i+1}/{len(chunks)}: Not found, asking next.")



                continue



            



            if len(resp) < 100:  # Valid selectors are short



                log.info(f"Chain HTML found selector in chunk {i+1}: {resp}")



                return resp



                



        log.warning(f"Chain HTML could not find {target_desc} in any chunk.")



        return ""







    def plan(self, goal: str, context: str = "") -> List[Step]:



        """Ask LLM to generate ordered step list for a goal."""



        self.ensure_brain()







        prompt = (



            f"You are an AI agent controlling a real browser.\n"



            f"GOAL: {goal}\n"



            f"CONTEXT: {context}\n\n"



            f"List the ordered steps to achieve this goal.\n"



            f"One step per line, numbered. Be VERY specific.\n"



            f"Include: URLs to navigate, what text to type (in quotes), buttons to click.\n"



            f"Now list steps for: {goal}"



        )



        log.info(f"Planning: {goal}")



        response = self._query(prompt)







        steps = []



        for line in (response or "").strip().split("\n"):



            m = re.match(r"^[\d]+[.)]\s*(.+)", line.strip())



            if m:



                steps.append(Step(action=m.group(1).strip()))







        if not steps:



            steps = [Step(action=goal)]







        log.info(f"Plan: {len(steps)} steps")



        for i, s in enumerate(steps, 1):



            log.info(f"  {i}. {s.action}")



        return steps







    # ------------------------------------------------------------------ #



    #  Think — "where am I, what next?"                                   #



    # ------------------------------------------------------------------ #







    def think(self, situation: str, context: str = "") -> str:



        """



        Human-like check-in: I just did something. Where am I? What next?



        Called after EVERY step — exactly like a human pausing to assess.



        """



        page_state = self.read_page_state()



        prompt = (



            f"You are PocoPrime, an AI agent.\n"



            f"SITUATION: {situation}\n"



            f"CONTEXT: {context}\n"



            f"CURRENT PAGE STATE:\n{page_state}\n\n"



            f"What is the single most important next action?\n"



            f"One sentence. Be specific. Do not explain."



        )



        resp = self._query(prompt, timeout=30)



        result = resp.strip() if resp else "Continue with next planned step"



        log.info(f"Think → {result[:100]}")



        return result







    # ------------------------------------------------------------------ #



    #  Decide after each step                                             #



    # ------------------------------------------------------------------ #







    def _decide(self, goal: str, step_done: str,



                page_state: str, history: str) -> Dict:



        """Ask LLM: did that work? What's the status?"""



        prompt = (



            f"You are an AI agent.\n"



            f"GOAL: {goal}\n"



            f"STEP DONE: {step_done}\n"



            f"PAGE NOW:\n{page_state}\n"



            f"HISTORY: {history}\n\n"



            f'Reply in JSON: {{"status":"done|continue|stuck|error", '



            f'"next":"specific next action", "why":"brief reason"}}\n'



            f"done=goal achieved, continue=step worked, stuck=need alt, error=blocked"



        )



        resp = self._query(prompt, timeout=40)



        try:



            m = re.search(r'\{.*?\}', resp or "", re.DOTALL)



            if m:



                return json.loads(m.group())



        except Exception:



            pass



        # Text fallback



        if not resp:



            return {"status": "continue", "next": "", "why": "no response"}



        status = "continue"



        for kw, st in [("done", "done"), ("success", "done"),



                       ("stuck", "stuck"), ("fail", "stuck"),



                       ("error", "error"), ("captcha", "error")]:



            if kw in resp.lower():



                status = st; break



        return {"status": status, "next": resp[:200], "why": ""}







    # ------------------------------------------------------------------ #



    #  Execute action via Selenium                                        #



    # ------------------------------------------------------------------ #







    def _execute_action(self, action: str) -> str:



        if not self.driver:



            return "No driver"



        a = action.lower()



        try:



            from selenium.webdriver.common.by import By



            from selenium.webdriver.support.ui import WebDriverWait



            from selenium.webdriver.support import expected_conditions as EC



            from selenium.webdriver.common.keys import Keys







            url_m = re.search(r'https?://\S+', action)



            if url_m and any(x in a for x in ["navigate","go to","open","visit","http"]):



                self.driver.get(url_m.group())



                time.sleep(4)



                return f"Navigated to {url_m.group()}"







            if any(x in a for x in ["type","enter","fill","input"]):



                txt = re.search(r"['\"]([^'\"]+)['\"]", action)



                if txt:



                    for sel in ["input", "textarea", "[type='text']", "[type='password']"]:



                        try:



                            el = WebDriverWait(self.driver, 5).until(



                                EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))



                            el.clear()



                            el.send_keys(txt.group(1))



                            return f"Typed '{txt.group(1)}'"



                        except Exception:



                            continue







            if "click" in a:



                lbl = re.search(r"['\"]([^'\"]+)['\"]", action)



                lbl = lbl.group(1) if lbl else ""



                for loc in [



                    (By.XPATH, f"//button[contains(.,'{lbl}')]"),



                    (By.XPATH, f"//a[contains(.,'{lbl}')]"),



                    (By.CSS_SELECTOR, "[type='submit']"),



                    (By.CSS_SELECTOR, "button"),



                ]:



                    try:



                        el = WebDriverWait(self.driver, 5).until(



                            EC.element_to_be_clickable(loc))



                        self.driver.execute_script("arguments[0].click();", el)



                        return f"Clicked '{lbl}'"



                    except Exception:



                        continue







            if any(x in a for x in ["wait","pause","sleep"]):



                n = re.search(r"(\d+)", a)



                s = int(n.group(1)) if n else 3



                time.sleep(s)



                return f"Waited {s}s"







        except Exception as e:



            return f"Action error: {e}"



        return f"No match: {action[:60]}"







    # ------------------------------------------------------------------ #



    #  MAIN LOOP — true human-like continuous agent                       #



    # ------------------------------------------------------------------ #







    def execute_plan(self, goal: str, context: str = "",



                     step_callback: Optional[Callable] = None) -> bool:



        """



        Human-like agent loop:







          1. Check brain alive



          2. Plan steps



          3. For each step:



             a. Do it



             b. Read page — "where am I?"



             c. Ask brain — "what next?"



             d. If error → consult brain → try fix → read → ask again



             e. If done → stop



             f. If stuck → ask brain for alternative → retry



          ↑ Repeat forever until goal achieved







        This is exactly how a human uses a browser.



        """



        log.info("=" * 55)



        log.info(f"BRAIN AGENT: {goal}")



        log.info("=" * 55)







        # Step 0: Check brain



        self.ensure_brain()







        steps    = self.plan(goal, context)



        idx      = 0



        stuck_n  = 0







        while idx < len(steps) and idx < self.max_steps:



            step = steps[idx]



            step.attempts += 1







            log.info(f"── Step {idx+1}/{len(steps)} ─────────────────────────")



            log.info(f"   ACTION: {step.action}")







            # a. Do the action



            result = self._execute_action(step.action)



            log.info(f"   RESULT: {result}")







            # b. Read page — "where am I right now?"



            page = self.read_page_state()



            log.info(f"   PAGE: {page[:80].replace(chr(10),' ')}")







            # c. Ask brain — "what happened? what next?"



            hist = " | ".join(



                f"{h['step'][:30]}:{h['status']}"



                for h in (self.history or [])[-3:]



            )



            decision = self._decide(goal, step.action, page, hist)



            status   = decision.get("status", "continue")



            nxt      = decision.get("next", "")



            log.info(f"   BRAIN: {status} — {decision.get('why','')[:60]}")







            # Record



            self.history.append({



                "step": step.action, "result": result,



                "page": page[:80], "status": status



            })







            if step_callback:



                step_callback(idx + 1, step.action, status, page)







            # d/e/f. Handle decision



            if status == "done":



                log.info(f"GOAL ACHIEVED: {goal}")



                return True







            elif status == "continue":



                stuck_n = 0



                idx += 1



                if nxt:



                    steps.insert(idx, Step(action=nxt))







            elif status in ("stuck", "error"):



                stuck_n += 1



                # Ask brain for alternative (every time, no limit)



                alt = self.think(



                    f"I tried: '{step.action}' and got stuck/error. Goal: {goal}",



                    context=f"Page: {page[:200]}"



                )



                log.info(f"   ALTERNATIVE: {alt}")



                steps[idx] = Step(action=alt)



                if stuck_n > 5:



                    # After 5 alternates on same step, skip and move on



                    log.warning("5 alternates tried — skipping step")



                    stuck_n = 0



                    idx += 1







        log.info(f"Plan complete. History: {len(self.history)} steps")



        return False







    # ------------------------------------------------------------------ #



    #  unstick — ask LLM for alternative                                  #



    # ------------------------------------------------------------------ #







    def unstick(self, goal: str, page: str, hist: str, problem: str) -> str:



        prompt = (



            f"Agent. Goal: {goal}. Problem: {problem}. Page: {page[:200]}. "



            f"History: {hist}. What DIFFERENT action? One sentence."



        )



        return (self._query(prompt, 30) or "Refresh page and retry").strip()



