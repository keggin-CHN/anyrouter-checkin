#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnyRouter.top 自动登录 & 余额推送
功能:
  - 每天北京时间 09:00 自动登录 anyrouter.top
  - 登录成功后等待 10 秒
  - 抓取当前余额并推送到 Telegram Bot
  - 失败时同样推送通知
"""

import os
import re
import time
import json
import logging
import asyncio
import requests
from datetime import datetime, timezone, timedelta

# ─────────────────────── 配置 ───────────────────────
BASE_URL    = "https://anyrouter.top"
USERNAME    = os.getenv("AR_USERNAME")
PASSWORD    = os.getenv("AR_PASSWORD")
TG_TOKEN    = os.getenv("TG_BOT_TOKEN")
TG_CHAT     = os.getenv("TG_CHAT_ID")

if not all([USERNAME, PASSWORD, TG_TOKEN, TG_CHAT]):
    raise ValueError("环境变量缺失，请检查 GitHub Secrets 配置 (AR_USERNAME, AR_PASSWORD, TG_BOT_TOKEN, TG_CHAT_ID)")

# 北京时间
BJT = timezone(timedelta(hours=8))

# ─────────────────────── 日志 ───────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anyrouter-checkin")


# ════════════════════════════════════════════════════
#  Telegram 通知
# ════════════════════════════════════════════════════
def send_tg(text: str) -> bool:
    """向 Telegram Bot 发送 HTML 格式消息"""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TG_CHAT,
        "text":       text,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        logger.info("✅ TG 消息发送成功")
        return True
    except Exception as e:
        logger.error(f"❌ TG 消息发送失败: {e}")
        return False


def fmt_balance(quota: int, used_quota: int) -> str:
    """将 new-api 配额值转换为可读余额字符串 (1 USD = 500,000 units)"""
    total_usd = quota / 500_000
    used_usd  = used_quota / 500_000
    remain    = total_usd - used_usd
    return (
        f"💰 剩余: <b>${remain:.4f}</b>\n"
        f"📊 总量: ${total_usd:.4f} | 已用: ${used_usd:.4f}"
    )


# ════════════════════════════════════════════════════
#  Playwright 登录核心
# ════════════════════════════════════════════════════
async def do_checkin() -> dict:
    """
    使用 Playwright Chromium 登录并获取余额。
    返回: {"success": bool, "balance": str | None, "error": str | None}
    """
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    result = {"success": False, "balance": None, "error": None}

    async with async_playwright() as pw:
        logger.info("🚀 启动 Chromium 浏览器 (headless)...")
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1440, "height": 900},
        )

        # 隐藏 webdriver 标志，防止反爬
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        page = await context.new_page()

        try:
            # ── 1. 打开登录页 ──
            logger.info(f"🌐 正在打开 {BASE_URL}/login ...")
            await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=90_000)

            # 等待 Cloudflare JS 挑战通过（最多 20 秒）
            logger.info("⏳ 等待 Cloudflare 验证...")
            await page.wait_for_function(
                "() => !document.title.includes('Just a moment') && document.readyState === 'complete'",
                timeout=30_000,
            )
            await page.wait_for_timeout(2_000)

            logger.info(f"📄 页面标题: {await page.title()}")

            # ── 1.5 关闭可能存在的系统公告弹窗 ──
            try:
                # 尝试查找包含“关闭”相关字眼的按钮，设置较短超时以免卡住
                close_btn_sels = [
                    'button:has-text("关闭公告")',
                    'button:has-text("今日关闭")',
                    'button:has-text("我知道了")',
                    '.semi-modal-close',  # semi design 的关闭按钮
                ]
                for sel in close_btn_sels:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        logger.info(f"🛑 发现系统公告弹窗，尝试关闭: {sel}")
                        await btn.click(force=True)
                        await page.wait_for_timeout(1000)
            except Exception as e:
                logger.info(f"关闭弹窗时发生错误（忽略）: {e}")

            # ── 2. 定位用户名输入框 ──
            username_sel = [
                'input[name="username"]',
                'input[placeholder*="用户名"]',
                'input[placeholder*="Username"]',
                '#username',
                'input[type="text"]:first-of-type',
            ]
            username_loc = None
            
            # 如果没找到输入框，可能需要先点击右上角的登录按钮
            try:
                for sel in username_sel:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        username_loc = loc
                        break
            except Exception:
                pass
                
            if not username_loc:
                logger.info("尝试点击右上角【登录】按钮...")
                try:
                    login_btn = page.locator('button:has-text("登录"), a:has-text("登录")').first
                    await login_btn.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                except Exception as e:
                    logger.info(f"点击登录按钮失败: {e}")

            for sel in username_sel:
                loc = page.locator(sel).first
                try:
                    await loc.wait_for(state="visible", timeout=5_000)
                    username_loc = loc
                    logger.info(f"✔ 找到用户名输入框: {sel}")
                    break
                except PWTimeout:
                    continue

            if username_loc is None:
                raise RuntimeError("未找到用户名输入框，请检查页面结构")

            # ── 3. 定位密码输入框 ──
            password_loc = page.locator('input[type="password"]').first
            try:
                await password_loc.wait_for(state="visible", timeout=5_000)
            except PWTimeout:
                raise RuntimeError("未找到密码输入框")

            # ── 4. 填写并提交 ──
            logger.info("✏️  填写登录凭据...")
            # 使用 force=True 忽略遮罩层（如 semi-portal）拦截
            await username_loc.fill(USERNAME, force=True)
            await page.wait_for_timeout(300)

            await password_loc.fill(PASSWORD, force=True)
            await page.wait_for_timeout(300)

            # 查找提交按钮
            submit_sels = [
                'button[type="submit"]',
                'button:has-text("登录")',
                'button:has-text("Login")',
                'button:has-text("Sign in")',
                'input[type="submit"]',
            ]
            submitted = False
            for sel in submit_sels:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    try:
                        await btn.click(force=True, timeout=3_000)
                        submitted = True
                        logger.info(f"🖱  点击提交按钮: {sel}")
                        break
                    except Exception:
                        continue

            if not submitted:
                logger.info("⌨️  按 Enter 提交表单")
                await password_loc.press("Enter")

            # ── 5. 等待登录完成 ──
            logger.info("⏳ 等待登录完成...")
            for _ in range(15):
                await page.wait_for_timeout(2000)
                if "login" not in page.url:
                    break
            
            if "login" in page.url:
                raise RuntimeError("登录后页面未跳转，可能密码错误或触发了其他验证")

            current_url = page.url
            logger.info(f"✅ 登录成功! 当前 URL: {current_url}")

            # ── 6. 等待 10 秒（任务要求）──
            logger.info("⏳ 等待 10 秒后获取余额...")
            await asyncio.sleep(10)

            # ── 7. 获取余额 ──
            balance_str = await _get_balance(page, context)
            result["success"] = True
            result["balance"] = balance_str

        except Exception as exc:
            import html
            logger.error(f"❌ 执行失败: {exc}")
            result["error"] = html.escape(str(exc))
            try:
                await page.screenshot(path="failure.png", full_page=True)
                logger.info("📸 失败截图已保存到 failure.png")
            except Exception:
                pass

        finally:
            await context.close()
            await browser.close()

    return result


async def _get_balance(page, context) -> str:
    """
    多策略获取余额:
    1. 读取 localStorage 中的 user 数据
    2. 调用 /api/user/self (带 session cookie)
    3. 从页面 DOM 元素提取
    """
    # 策略 1: API /api/user/self (携带浏览器 cookies)
    try:
        # 用页面内 fetch 发起请求，自动带上所有 Cookie
        api_resp = await page.evaluate("""
            async () => {
                try {
                    const r = await fetch('/api/user/self', {credentials: 'include'});
                    return await r.json();
                } catch(e) {
                    return null;
                }
            }
        """)
        if api_resp and api_resp.get("success"):
            user = api_resp.get("data", {})
            quota      = user.get("quota", 0)
            used_quota = user.get("used_quota", 0)
            if quota > 0 or used_quota > 0:
                logger.info(f"🔌 API: quota={quota}, used={used_quota}")
                return fmt_balance(int(quota), int(used_quota))
    except Exception as e:
        logger.warning(f"API 获取余额失败: {e}")

    # 策略 2: localStorage
    try:
        user_json = await page.evaluate(
            "() => localStorage.getItem('user') || sessionStorage.getItem('user')"
        )
        if user_json:
            user = json.loads(user_json)
            quota      = user.get("quota", 0)
            used_quota = user.get("used_quota", 0)
            if quota > 0 or used_quota > 0:
                logger.info(f"📦 localStorage: quota={quota}, used={used_quota}")
                return fmt_balance(int(quota), int(used_quota))
    except Exception as e:
        logger.warning(f"localStorage 读取失败: {e}")

    # 策略 3: 导航到个人页面再读 DOM
    try:
        for path in ["/dashboard", "/profile", "/panel", "/"]:
            await page.goto(f"https://anyrouter.top{path}", timeout=15_000)
            await page.wait_for_timeout(3_000)
            
            # 尝试点击潜在的“签到”按钮
            try:
                checkin_sels = ['button:has-text("签到")', 'span:has-text("签到")', 'a:has-text("签到")']
                for csel in checkin_sels:
                    cbtn = page.locator(csel).first
                    if await cbtn.count() > 0 and await cbtn.is_visible():
                        await cbtn.click(force=True, timeout=2000)
                        logger.info(f"🎁 点击签到按钮: {csel}")
                        await page.wait_for_timeout(2000)
                        break
            except Exception:
                pass

            # DOM 查找余额文本
            for sel in [
                '[class*="balance"]', '[class*="quota"]', '[class*="credit"]',
                '.statistic-value', '.ant-statistic-content-value',
                'div:has-text("余额")', 'div:has-text("剩余")',
            ]:
                try:
                    texts = await page.locator(sel).all_inner_texts()
                    for txt in texts:
                        txt = txt.strip()
                        if txt and len(txt) < 80 and re.search(r"\d+\.?\d*", txt):
                            logger.info(f"🔍 DOM 找到余额元素: {sel} → {txt!r}")
                            
                            # 尝试提取具体的美元数值
                            usd_matches = re.findall(r"\$\s*\d+\.\d+", txt)
                            if len(usd_matches) >= 2:
                                clean_txt = f"当前余额: {usd_matches[0]} | 历史消耗: {usd_matches[1]}"
                            elif len(usd_matches) == 1:
                                clean_txt = f"{usd_matches[0]}"
                            else:
                                # 去掉多余的回车，变成单行
                                clean_txt = re.sub(r"\s+", " ", txt)
                                
                            return f"💰 余额/额度: <b>{clean_txt}</b>"
                except Exception as e:
                    pass
    except Exception as e:
        logger.warning(f"DOM 页面读取失败: {e}")

    return "余额获取失败（请手动登录查看）"


# ════════════════════════════════════════════════════
#  主入口
# ════════════════════════════════════════════════════
async def main():
    now_bjt = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"═══ AnyRouter 自动签到开始 [{now_bjt} BJT] ═══")

    result = await do_checkin()

    now_bjt = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")

    if result["success"]:
        msg = (
            f"✅ <b>AnyRouter 每日签到成功</b>\n\n"
            f"🌐 站点: anyrouter.top\n"
            f"👤 用户: <code>{USERNAME}</code>\n"
            f"{result['balance']}\n"
            f"⏰ 时间: {now_bjt} (BJT)\n\n"
            f"<i>🤖 由 GitHub Actions 自动执行</i>"
        )
        logger.info("🎉 签到成功，推送 TG 通知...")
    else:
        msg = (
            f"❌ <b>AnyRouter 签到失败</b>\n\n"
            f"🌐 站点: anyrouter.top\n"
            f"👤 用户: <code>{USERNAME}</code>\n"
            f"❗ 错误: <code>{result['error']}</code>\n"
            f"⏰ 时间: {now_bjt} (BJT)\n\n"
            f"<i>🤖 请检查 GitHub Actions 日志</i>"
        )
        logger.error("💥 签到失败，推送 TG 错误通知...")

    send_tg(msg)
    logger.info("═══ 签到任务结束 ═══")
    
    if not result["success"]:
        import sys
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
