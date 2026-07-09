#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnyRouter.top 纯协议自动签到 (无浏览器)
功能:
  - 破解 acw_sc__v2 JS challenge (Node.js 子进程, 无浏览器)
  - 用户名/密码登录获取 Bearer token
  - 签到领配额
  - 获取余额推送到 Telegram
"""

import os
import json
import logging
import subprocess
import requests
from datetime import datetime, timezone, timedelta

# ─────────────────────── 配置 ───────────────────────
BASE_URL = "https://anyrouter.top"
USERNAME = os.getenv("AR_USERNAME")
PASSWORD = os.getenv("AR_PASSWORD")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT  = os.getenv("TG_CHAT_ID")

if not all([USERNAME, PASSWORD, TG_TOKEN, TG_CHAT]):
    raise ValueError(
        "环境变量缺失，请检查 GitHub Secrets 配置 "
        "(AR_USERNAME, AR_PASSWORD, TG_BOT_TOKEN, TG_CHAT_ID)"
    )

BJT = timezone(timedelta(hours=8))

# ─────────────────────── 日志 ───────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anyrouter-checkin")


# ════════════════════════════════════════════════════
#  acw_sc__v2 Challenge Solver
# ════════════════════════════════════════════════════

# Node.js 脚本：获取 challenge 页面 → 执行 JS → 输出 acw_sc__v2 cookie
# 不需要浏览器，只需要 Node.js 运行时来执行 challenge JS
_CHALLENGE_SOLVER_JS = r"""
const https = require('https');
const zlib = require('zlib');

function fetch(url) {
    return new Promise((resolve, reject) => {
        https.get(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
            }
        }, res => {
            const chunks = [];
            res.on('data', c => chunks.push(c));
            res.on('end', () => {
                const buf = Buffer.concat(chunks);
                if (res.headers['content-encoding'] === 'gzip') {
                    zlib.gunzip(buf, (e, d) => resolve(e ? buf.toString() : d.toString()));
                } else {
                    resolve(buf.toString());
                }
            });
        }).on('error', reject);
    });
}

async function main() {
    const html = await fetch('https://anyrouter.top/');
    const m = html.match(/arg1='([A-F0-9]+)'/);
    if (!m) { process.exit(1); }

    let cookieResult = '';
    const mockDoc = new Proxy({}, {
        set(t, p, v) {
            t[p] = v;
            if (String(p) === 'cookie') cookieResult = String(v);
            return true;
        },
        get(t, p) {
            if (p === 'location') return new Proxy({}, { get(_, k) { return k === 'reload' ? () => {} : undefined; } });
            if (p === 'cookie') return '';
            return t[p];
        }
    });

    const sm = html.match(/<script>([\s\S]+?)<\/script>/);
    if (sm) {
        try { new Function('document', sm[1] + ';')(mockDoc); } catch (e) {}
    }

    const acwMatch = cookieResult.match(/acw_sc__v2=([^;]+)/);
    if (!acwMatch) { process.exit(1); }

    process.stdout.write(JSON.stringify({ arg1: m[1], cookie: acwMatch[1] }));
}
main();
"""


def solve_acw_sc_v2() -> str | None:
    """
    解决 acw_sc__v2 challenge，返回 cookie 值。
    使用 Node.js 执行 challenge JS (纯协议，无浏览器)。
    """
    try:
        result = subprocess.run(
            ["node", "-e", _CHALLENGE_SOLVER_JS],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            acw = data.get("cookie")
            if acw:
                logger.info(f"✅ acw_sc__v2 challenge 已解决")
                return acw
    except Exception as e:
        logger.warning(f"Challenge solver 失败: {e}")

    logger.error("❌ acw_sc__v2 challenge 解决失败")
    return None


# ════════════════════════════════════════════════════
#  Telegram 通知
# ════════════════════════════════════════════════════
def send_tg(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TG_CHAT,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=30)
        r.raise_for_status()
        logger.info("✅ TG 消息发送成功")
        return True
    except Exception as e:
        logger.error(f"❌ TG 消息发送失败: {e}")
        return False


def fmt_balance(quota: int, used_quota: int) -> str:
    total_usd = quota / 500_000
    used_usd  = used_quota / 500_000
    remain    = total_usd - used_usd
    return (
        f"💰 剩余: <b>${remain:.4f}</b>\n"
        f"📊 总量: ${total_usd:.4f} | 已用: ${used_usd:.4f}"
    )


# ════════════════════════════════════════════════════
#  纯协议签到核心
# ════════════════════════════════════════════════════
def do_checkin() -> dict:
    """
    纯 HTTP 协议完成签到:
    1. 破解 acw_sc__v2 challenge
    2. 用户名/密码登录获取 token
    3. 签到
    4. 获取余额
    """
    result = {"success": False, "balance": None, "error": None}
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })

    try:
        # ── 1. 破解 acw_sc__v2 ──
        logger.info("🔐 破解 acw_sc__v2 challenge...")
        acw_value = solve_acw_sc_v2()
        if not acw_value:
            raise RuntimeError("acw_sc__v2 challenge 破解失败")
        sess.cookies.set("acw_sc__v2", acw_value, domain="anyrouter.top", path="/")

        # ── 2. 验证 API 可访问 ──
        logger.info("✅ 验证 API 可访问...")
        status_resp = sess.get(f"{BASE_URL}/api/status", timeout=15)
        try:
            status_data = status_resp.json()
            logger.info(f"API 状态: success={status_data.get('success', 'N/A')}")
        except json.JSONDecodeError:
            raise RuntimeError("acw_sc__v2 cookie 未生效，API 仍返回 HTML")

        # ── 3. 登录 ──
        logger.info("🔑 登录中...")
        login_resp = sess.post(
            f"{BASE_URL}/api/user/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=15,
        )
        login_data = login_resp.json()

        if not login_data.get("success", False):
            error_msg = login_data.get("message", "未知错误")
            raise RuntimeError(f"登录失败: {error_msg}")

        # 提取 token
        token = login_data.get("data", "")
        if not token:
            raise RuntimeError("登录成功但未返回 token")

        logger.info(f"✅ 登录成功! token: {token[:20]}...")
        sess.headers["Authorization"] = f"Bearer {token}"

        # ── 4. 签到 ──
        logger.info("🎁 执行签到...")
        signin_resp = sess.post(f"{BASE_URL}/api/user/sign_in", timeout=15)
        signin_data = signin_resp.json()

        if signin_data.get("success"):
            earned = signin_data.get("data", "")
            logger.info(f"🎉 签到成功! 获得: {earned}")
        else:
            msg = signin_data.get("message", "")
            if "已签到" in msg or "already" in msg.lower():
                logger.info(f"ℹ️ 今日已签到: {msg}")
            else:
                logger.warning(f"⚠️ 签到返回: {msg}")

        # ── 5. 获取余额 ──
        logger.info("💰 获取余额...")
        user_resp = sess.get(f"{BASE_URL}/api/user/self", timeout=15)
        user_data = user_resp.json()

        if user_data.get("success"):
            user = user_data.get("data", {})
            quota      = int(user.get("quota", 0))
            used_quota = int(user.get("used_quota", 0))
            result["balance"] = fmt_balance(quota, used_quota)
            logger.info(f"💰 余额获取成功")
        else:
            result["balance"] = "余额获取失败（但签到成功）"
            logger.warning(f"余额获取失败: {user_data}")

        result["success"] = True

    except Exception as exc:
        logger.error(f"❌ 执行失败: {exc}")
        result["error"] = str(exc)

    return result


# ════════════════════════════════════════════════════
#  主入口
# ════════════════════════════════════════════════════
def main():
    now_bjt = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"═══ AnyRouter 纯协议签到开始 [{now_bjt} BJT] ═══")

    result = do_checkin()

    now_bjt = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")

    if result["success"]:
        msg = (
            f"✅ <b>AnyRouter 每日签到成功</b>\n\n"
            f"🌐 站点: anyrouter.top\n"
            f"👤 用户: <code>{USERNAME}</code>\n"
            f"{result['balance']}\n"
            f"⏰ 时间: {now_bjt} (BJT)\n\n"
            f"<i>🤖 由 GitHub Actions 纯协议自动执行</i>"
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
    main()
