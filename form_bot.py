#!/usr/bin/env python3
"""
Google Form Auto-Filler Bot
----------------------------
- Reads personal info from config.json
- Uses Gemini API to answer MCQ / short-answer questions
- Opens the form in Chrome, fills it out, then waits for you to review & submit

Usage:
    python3 form_bot.py <google_form_url>
    python3 form_bot.py https://forms.gle/xxxxxx
"""

import sys
import json
import time
import re
import os
import traceback
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# -- Dependency check ----------------------------------------------------------
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from google import genai
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Run:  pip install selenium google-genai")
    sys.exit(1)

# -- Config --------------------------------------------------------------------
CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    if not CONFIG_PATH.exists():
        print(f"[ERROR] config.json not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return cfg

# -- Gemini helper -------------------------------------------------------------
def ask_gemini(client, gemini_model, question_text: str, options: list[str]) -> str:
    """Ask Gemini to pick the best MCQ option. Returns the option text."""
    options_text = "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options))
    prompt = (
        f"You are answering a multiple-choice question in a form.\n\n"
        f"Question: {question_text}\n\n"
        f"Options:\n{options_text}\n\n"
        f"Reply with ONLY the exact text of the best answer option, nothing else."
    )
    try:
        response = client.models.generate_content(model=gemini_model, contents=prompt)
        answer = response.text.strip()
        # Try to match the answer back to one of the options (fuzzy)
        answer_lower = answer.lower()
        for opt in options:
            if opt.lower() in answer_lower or answer_lower in opt.lower():
                return opt
        # Fallback: return first option if nothing matched
        print(f"  [GEMINI] Raw answer: '{answer}' - no exact match, using option 1")
        return options[0]
    except Exception as e:
        print(f"  [GEMINI ERROR] {e} - defaulting to option 1\n{traceback.format_exc()}")
        return options[0]

def ask_gemini_text(client, gemini_model, question_text: str) -> str:
    """Ask Gemini for a short text answer."""
    prompt = (
        f"You are filling out a form. Answer this question briefly and accurately.\n\n"
        f"Question: {question_text}\n\n"
        f"Reply with ONLY the answer, no explanation."
    )
    try:
        response = client.models.generate_content(model=gemini_model, contents=prompt)
        return response.text.strip()
    except Exception as e:
        print(f"  [GEMINI ERROR TEXT] {e}\n{traceback.format_exc()}")
        return ""

# -- Personal info matcher -----------------------------------------------------
def find_personal_answer(label: str, personal_info: dict) -> str | None:
    """
    Try to match a form field label to a key in personal_info.
    Case-insensitive, partial match.
    """
    label_lower = label.lower().strip()
    # Direct match
    for key, val in personal_info.items():
        if key.lower() == label_lower:
            return val
    # Partial match (label contains key or key contains label)
    # Sort by descending key length to prioritize longer matches (e.g., "Branch-Division" before "Branch")
    for key, val in sorted(personal_info.items(), key=lambda x: len(x[0]), reverse=True):
        if key.lower() in label_lower or label_lower in key.lower():
            return val
    return None

# -- Browser setup -------------------------------------------------------------
def create_driver(cfg: dict):
    headless = cfg["browser"].get("headless", False)
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1200,900")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Use Brave if specified
    if "brave_binary_path" in cfg["browser"]:
        opts.binary_location = cfg["browser"]["brave_binary_path"]

    try:
        # Try default chromedriver on PATH first
        driver = webdriver.Chrome(options=opts)
    except Exception:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.core.os_manager import ChromeType
            
            # Setup driver manager for Brave if specified, else generic Chrome
            chrome_type = ChromeType.BRAVE if "brave_binary_path" in cfg["browser"] else ChromeType.GOOGLE
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager(chrome_type=chrome_type).install()), options=opts
            )
        except Exception as e:
            print(f"[ERROR] Could not start Chrome: {e}")
            print("Make sure Google Chrome is installed.")
            sys.exit(1)
    return driver

# -- Form filling logic --------------------------------------------------------
def slow_type(element, text: str, delay: float = 0.05):
    """Type text slowly so the page can react."""
    element.clear()
    for ch in str(text):
        element.send_keys(ch)
        time.sleep(delay)

def fill_form(driver, cfg: dict, client, gemini_model):
    personal_info = cfg["personal_info"]
    slow_ms       = cfg["browser"].get("slow_mode_ms", 500) / 1000
    wait          = WebDriverWait(driver, 15)

    print("\n[BOT] Waiting for form to load...")
    try:
        # Wait until the form question containers are visible in the DOM
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-params], div.Qr7Oae, div.freebirdFormviewerComponentsQuestionBaseRoot")))
    except Exception:
        print("[WARN] Form took too long to load or no questions found immediately.")
    time.sleep(1.0) # Additional buffer for JavaScript frameworks to finish rendering

    pages_done = 0
    while True:
        pages_done += 1
        print(f"\n[BOT] -- Processing page {pages_done} --")

        # Give the page a moment to settle
        time.sleep(1.5)

        # Handle out-of-band email collection fields that aren't inside regular question blocks
        email_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='email'].whsOnd, input[autocomplete='email'].whsOnd")
        for em in email_inputs:
            if em.is_displayed():
                current_val = em.get_attribute("data-initial-value") or em.get_attribute("value")
                if not current_val:
                    email_ans = personal_info.get("email", personal_info.get("email id", ""))
                    if email_ans:
                        print(f"[BOT] Found Email field outside question block, filling: {email_ans}")
                        slow_type(em, email_ans)
                    else:
                        print("[BOT] Found Email field but no email in config.json")

        # Grab all question blocks
        question_blocks = driver.find_elements(
            By.CSS_SELECTOR, "div[data-params], div.Qr7Oae"
        )
        if not question_blocks:
            # Fallback selector
            question_blocks = driver.find_elements(By.CSS_SELECTOR, "div.freebirdFormviewerComponentsQuestionBaseRoot")

        print(f"[BOT] Found {len(question_blocks)} question block(s)")

        for block in question_blocks:
            try:
                process_question_block(block, personal_info, gemini_model, slow_ms, driver)
            except Exception as e:
                print(f"  [WARN] Could not process a block: {e}")

        # Check if there's a "Next" button (multi-page form)
        next_btn = find_next_button(driver)
        if next_btn:
            print("\n[BOT] Found 'Next' button — moving to next page...")
            time.sleep(slow_ms)
            next_btn.click()
            time.sleep(2)
        else:
            print("\n[BOT] [DONE] All questions filled!")
            print("[BOT] 👀 Please REVIEW the form in the browser window.")
            print("[BOT] 📝 When you're happy, click the SUBMIT button manually.")
            print("[BOT] (Script will keep the browser open until you close it)")
            break

def find_next_button(driver):
    """Look for a Next / Continue button (not Submit)."""
    # Specifically target Google Forms form navigation buttons
    # Google Forms button structure usually has a specific jsname or data-value
    # But text analysis is safest. We just need to be very strict about what's clickable.
    for selector in [
        "//div[@role='button']//span[text()='Next']/..",
        "//div[@role='button']//span[text()='Continue']/..",
        "//div[@role='button' and .//span[text()='Next']]",
        "//div[@role='button' and .//span[text()='Continue']]",
    ]:
        try:
            btns = driver.find_elements(By.XPATH, selector)
            for btn in btns:
                # Ensure it's not hidden, and ensure it's not a disabled button
                if btn.is_displayed() and btn.is_enabled() and btn.get_attribute("aria-disabled") != "true":
                    return btn
        except Exception:
            pass
            
    # Fallback to general text check, but highly restrictive
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, "div[role='button']")
        for btn in btns:
            if btn.is_displayed() and btn.is_enabled() and btn.get_attribute("aria-disabled") != "true":
                text = btn.text.strip().lower()
                if "submit" not in text and ("next" == text or "continue" == text):
                    return btn
    except Exception:
        pass
        
    return None

def process_question_block(block, personal_info, gemini_model, slow_ms, driver):
    """Detect question type and fill accordingly."""

    # -- Get question label --
    label = ""
    for sel in [
        "div[role='heading']",
        ".M7eMe",
        ".freebirdFormviewerComponentsQuestionBaseTitle",
        "span[dir='auto']",
        ".exportLabel",
    ]:
        try:
            el = block.find_element(By.CSS_SELECTOR, sel)
            label = el.text.strip()
            if label:
                break
        except Exception:
            pass

    if not label:
        return

    print(f"\n  [Q] {label[:80]}")

    # DEBUG: Dump the HTML of the first question block to investigate DOM structure
    if "First Name" in label or "Full name" in label:
        with open("debug_block.html", "w", encoding="utf-8") as f:
            f.write(block.get_attribute('outerHTML'))
        print("  [DEBUG] Dumped HTML to debug_block.html")

    # -- SHORT ANSWER / PARAGRAPH (text input) --
    # Google Forms uses specific classes for text inputs, not just type='text'
    text_inputs = block.find_elements(By.CSS_SELECTOR, "input.whsOnd.zHQkBf, textarea.KHxj8b.tL9Q4c, input[type='text']")
    if text_inputs:
        inp = text_inputs[0]
        if not inp.is_displayed():
            return

        # Try personal info first
        answer = find_personal_answer(label, personal_info)
        
        # If the user explicitly provided an empty string (""), skip this field entirely.
        if answer == "":
            print(f"  [PERSONAL] → (Skipping, configured as empty)")
            return
            
        if answer is not None:
            print(f"  [PERSONAL] → {answer}")
        else:
            # Ask Gemini
            answer = ask_gemini_text(client, gemini_model, label)
            print(f"  [GEMINI]   -> {answer}")

        slow_type(inp, answer)
        time.sleep(slow_ms)
        return

    # -- MULTIPLE CHOICE (radio) --
    radio_options = block.find_elements(By.CSS_SELECTOR, "div[role='radio'], label.docssharedWizToggleLabeledLabelWrapper")
    if radio_options:
        option_texts = []
        for opt in radio_options:
            t = opt.text.strip()
            if t:
                option_texts.append(t)

        if not option_texts:
            return

        print(f"  [MCQ] Options: {option_texts}")
        
        answer = find_personal_answer(label, personal_info)
        if answer == "":
            print(f"  [PERSONAL] → (Skipping, configured as empty)")
            return
            
        if answer is not None:
            chosen = answer
            print(f"  [PERSONAL] → {chosen}")
        else:
            chosen = ask_gemini(client, gemini_model, label, option_texts)
            print(f"  [GEMINI] -> {chosen}")

        for opt in radio_options:
            if opt.text.strip().lower() == chosen.lower():
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", opt)
                    time.sleep(0.3)
                    opt.click()
                    time.sleep(slow_ms)
                    return
                except Exception:
                    pass
        # Fallback: click first
        try:
            radio_options[0].click()
        except Exception:
            pass
        return

    # -- CHECKBOXES (multi-select) --
    checkbox_options = block.find_elements(By.CSS_SELECTOR, "div[role='checkbox']")
    if checkbox_options:
        option_texts = [c.text.strip() for c in checkbox_options if c.text.strip()]
        print(f"  [CHECKBOX] Options: {option_texts}")
        
        answer = find_personal_answer(label, personal_info)
        if answer == "":
            print(f"  [PERSONAL] → (Skipping, configured as empty)")
            return
            
        if answer is not None:
            chosen = answer
            print(f"  [PERSONAL] → {chosen}")
        else:
            chosen = ask_gemini(client, gemini_model, label, option_texts)
            print(f"  [GEMINI] -> {chosen}")

        for cb in checkbox_options:
            if cb.text.strip().lower() == chosen.lower():
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", cb)
                    time.sleep(0.3)
                    cb.click()
                    time.sleep(slow_ms)
                    return
                except Exception:
                    pass
        return

    # -- DROPDOWN --
    # Google Forms custom dropdowns
    dropdowns = block.find_elements(By.CSS_SELECTOR, "div[role='listbox']")
    if dropdowns:
        dd = dropdowns[0]
        try:
            # 1. Click to open dropdown menu
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dd)
            time.sleep(0.5)
            # Try javascript click first to avoid ElementNotInteractable
            driver.execute_script("arguments[0].click();", dd)
            time.sleep(1.0) # Wait for animation

            # 2. Get all visible options dynamically loaded at the end of the DOM
            # Google forms renders the options list outside the question block once clicked!
            items = driver.find_elements(By.CSS_SELECTOR, "div[role='option'][data-value]")
            opts = [i.get_attribute("data-value").strip() for i in items if i.get_attribute("data-value") and i.get_attribute("data-value").strip() != ""]
            
            if opts:
                answer = find_personal_answer(label, personal_info)
                if answer == "":
                    print(f"  [DROPDOWN PERSONAL] → (Skipping, configured as empty)")
                    return
                    
                if answer is not None:
                    chosen = answer
                    print(f"  [DROPDOWN PERSONAL] → {chosen}")
                else:
                    chosen = ask_gemini(client, gemini_model, label, opts)
                    print(f"  [DROPDOWN GEMINI] -> {chosen}")
                
                # Try exact match first on data-value
                clicked = False
                for item in items:
                    val = item.get_attribute("data-value")
                    if val and val.strip().lower() == chosen.lower():
                        driver.execute_script("arguments[0].click();", item)
                        clicked = True
                        break
                
                # Partial match fallback
                if not clicked:
                    for item in items:
                        val = item.get_attribute("data-value")
                        if val and val.strip():
                            t = val.strip().lower()
                            if (chosen.lower() in t or t in chosen.lower()):
                                driver.execute_script("arguments[0].click();", item)
                                clicked = True
                                break
                        
                # Fallback to first valid option
                if not clicked and items:
                    for item in items:
                        val = item.get_attribute("data-value")
                        if val and val.strip():
                            driver.execute_script("arguments[0].click();", item)
                            break
                            
            time.sleep(slow_ms)
        except Exception as e:
            print(f"  [DROPDOWN ERROR] {e}")
        return

    # -- LINEAR SCALE --
    scale_options = block.find_elements(By.CSS_SELECTOR, "div[role='radio'][data-value]")
    if scale_options:
        mid = len(scale_options) // 2
        try:
            scale_options[mid].click()
            print(f"  [SCALE] Picked middle option")
        except Exception:
            pass
        return

# -- Main ----------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 form_bot.py <google_form_url>")
        print("Example: python3 form_bot.py https://forms.gle/xxxxxxx")
        sys.exit(1)

    url = sys.argv[1]
    if "forms" not in url and "forms.gle" not in url:
        print("[WARN] URL doesn't look like a Google Form. Proceeding anyway...")

    print("=" * 60)
    print("  Google Form Auto-Filler Bot  [BOT]")
    print("=" * 60)

    # Load config
    cfg = load_config()
    print(f"[BOT] Config loaded")
    print(f"[BOT] Personal info keys: {list(cfg['personal_info'].keys())[:5]}...")

    # Init Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not found in environment variables or .env file.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    gemini_model = cfg.get("gemini_model", "gemini-1.5-flash")
    print(f"[BOT] Gemini API ready")

    # Launch browser
    print(f"[BOT] Launching browser...")
    driver = create_driver(cfg)
    driver.get(url)
    print(f"[BOT] Opened: {url}")

    try:
        fill_form(driver, cfg, client, gemini_model)
        # Keep browser open for user review
        input("\n[BOT] Press ENTER in this terminal to close the browser...\n")
    except KeyboardInterrupt:
        print("\n[BOT] Interrupted by user.")
    finally:
        driver.quit()
        print("[BOT] Browser closed. Bye!")

if __name__ == "__main__":
    main()
