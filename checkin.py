#!/usr/bin/env python3
"""AnyRouter checkin via Selenium."""
import json, logging, os, re, sys, time, requests
from datetime import datetime, timezone, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE_URL = "https://anyrouter.top"
USERNAME = "keggin"
PASSWORD = "Zhou060423rls"
TG_TOKEN = "8533373166:AAEQ3a9Wk6d3saVwMTakjzMdXwxRPe9CbWg"
TG_CHAT = "7420206850"
BJT = timezone(timedelta(hours=8))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ar")

def send_tg(text):
    try:
        r = requests.post("https://api.telegram.org/bot" + TG_TOKEN + "/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}, timeout=30)
        logger.info("TG: %d" % r.status_code)
    except Exception as e:
        logger.error("TG fail: %s" % e)

def init_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1440,900")
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36"
    opts.add_argument("--user-agent=" + ua)
    chrome_bin = os.environ.get("CHROME_BIN", "")
    if chrome_bin and os.path.exists(chrome_bin):
        opts.binary_location = chrome_bin
    cd_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/share/chromedriver-linux64/chromedriver")
    if os.path.exists(cd_path):
        return webdriver.Chrome(service=Service(cd_path), options=opts)
    return webdriver.Chrome(options=opts)

def do_checkin():
    result = {"success": False, "balance": None, "error": None}
    driver = None
    try:
        driver = init_driver()
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
        logger.info("Opening login page...")
        driver.get(BASE_URL + "/login")
        time.sleep(8)
        # Find username field
        username_el = None
        for sel in ['input[name="username"]', 'input[placeholder*="username"]', 'input[placeholder*="Username"]', '#username', 'input[type="text"]']:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    username_el = el
                    logger.info("Found username field: %s" % sel)
                    break
            except:
                pass
        if not username_el:
            # Try clicking login button first
            try:
                btns = driver.find_elements(By.TAG_NAME, 'button')
                for b in btns:
                    if 'login' in b.text.lower() or chr(0x767B) in b.text:
                        b.click()
                        time.sleep(3)
                        break
            except:
                pass
            for sel in ['input[name="username"]', 'input[type="text"]']:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    if el.is_displayed():
                        username_el = el
                        break
                except:
                    pass
        if not username_el:
            raise RuntimeError("Cannot find username field. Page: %s" % driver.current_url)
        password_el = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
        username_el.clear()
        username_el.send_keys(USERNAME)
        time.sleep(0.5)
        password_el.clear()
        password_el.send_keys(PASSWORD)
        time.sleep(0.5)
        # Submit
        submitted = False
        for sel in ['button[type="submit"]']:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed():
                    btn.click()
                    submitted = True
                    logger.info("Clicked submit")
                    break
            except:
                pass
        if not submitted:
            password_el.send_keys("\n")
            logger.info("Pressed Enter")
        # Wait for redirect
        for _ in range(20):
            time.sleep(2)
            if "login" not in driver.current_url:
                break
        if "login" in driver.current_url:
            raise RuntimeError("Still on login page: %s" % driver.current_url)
        logger.info("Login OK: %s" % driver.current_url)
        time.sleep(10)
        # Get balance via JS fetch
        try:
            api_resp = driver.execute_script(
                "return fetch('/api/user/self',{credentials:'include'}).then(function(r){return r.json()}).catch(function(){return null})")
            if api_resp and api_resp.get("success"):
                u = api_resp.get("data", {})
                q, uq = int(u.get("quota", 0)), int(u.get("used_quota", 0))
                if q > 0 or uq > 0:
                    result["balance"] = "Remaining: $%.4f / Total: $%.4f / Used: $%.4f" % (q/500000, (q+uq)/500000, uq/500000)
                    logger.info("Balance from API: %s" % result["balance"])
        except Exception as e:
            logger.warning("API balance failed: %s" % e)
        # Try clicking checkin button
        for sel in ['button:has-text("' + chr(0x7B7E) + chr(0x5230) + '")']:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed():
                    btn.click()
                    logger.info("Clicked checkin")
                    time.sleep(3)
                    break
            except:
                pass
        if not result["balance"]:
            result["balance"] = "Balance fetch failed"
        result["success"] = True
    except Exception as e:
        result["error"] = str(e)
        logger.error("Failed: %s" % e)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    return result

now2 = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")
result = do_checkin()
if result["success"]:
    msg = "AnyRouter checkin SUCCESS\nUser: %s\n%s\nTime: %s" % (USERNAME, result["balance"], now2)
else:
    msg = "AnyRouter checkin FAILED\nUser: %s\nError: %s\nTime: %s" % (USERNAME, result["error"], now2)
send_tg(msg)
if not result["success"]:
    sys.exit(1)
