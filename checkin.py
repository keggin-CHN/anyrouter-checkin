#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnyRouter.top 纯 Python 协议签到
- 纯 HTTP 协议，无浏览器
- 纯 Python 实现，无 Node.js / 第三方服务
- 单文件，无外部依赖（仅标准库 + requests）
"""

import os
import re
import json
import logging
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
        "环境变量缺失，请检查 GitHub Secrets "
        "(AR_USERNAME, AR_PASSWORD, TG_BOT_TOKEN, TG_CHAT_ID)"
    )

BJT = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("anyrouter-checkin")


# ════════════════════════════════════════════════════
#  acw_sc__v2 Challenge Solver (纯 Python)
# ════════════════════════════════════════════════════
#
# 算法逆向分析:
#   1. 网页返回 JS challenge，含 arg1 (40 字符 hex)
#   2. JS 用置换表 m 重排 arg1 字符位置
#   3. 重排结果与固定 key p 做逐字节 XOR
#   4. 输出 hex 字符串作为 acw_sc__v2 cookie
#
# key p 由 JS 混淆的 base64 解码函数得出，经逆向确认为常量。
# 置换表 m 同样是常量，从 JS 中直接提取。
#

# 置换表（从 JS 中提取，40 个元素对应 arg1 的 40 个字符）
_PERM = [
    0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26,
    0xa,  0x9,  0x13, 0x1f, 0x28, 0x1b, 0x16, 0x17,
    0x19, 0xd,  0x6,  0xb,  0x27, 0x12, 0x14, 0x8,
    0xe,  0x15, 0x20, 0x1a, 0x2,  0x1e, 0x7,  0x4,
    0x11, 0x5,  0x3,  0x1c, 0x22, 0x25, 0xc,  0x24,
]

# XOR key（从 JS a0j(0x115) 解码得出，经多次验证为常量）
_KEY_HEX = "3000176000856006061501533003690027800375"


def solve_acw_sc_v2(html: str) -> str | None:
    """
    从 challenge HTML 中提取 arg1，计算 acw_sc__v2 cookie 值。
    返回完整的 cookie 值字符串，失败返回 None。
    """
    m = re.search(r"arg1='([A-F0-9]{40})'", html)
    if not m:
        return None
    arg1 = m.group(1)

    # 步骤 1: 用置换表重排 arg1
    # JS 逻辑: for x in arg1: for z in perm: if perm[z]==x+1: q[z]=arg1[x]
    q = [''] * 40
    for x in range(40):
        for z in range(40):
            if _PERM[z] == x + 1:
                q[z] = arg1[x]
    permuted = ''.join(q)

    # 步骤 2: 逐字节 XOR
    # JS: parseInt(permuted.substr(i,2),16) ^ parseInt(key.substr(i,2),16)
    result = ''
    for i in range(0, 40, 2):
        a = int(permuted[i:i+2], 16) ^ int(_KEY_HEX[i:i+2], 16)
        result += format(a, '02x')

    return result


# ════════════════════════════════════════════════════
#  Telegram 通知
# ════════════════════════════════════════════════════
def send_tg(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
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
        # ── 1. 获取 challenge 并破解 ──
        logger.info("🔐 获取并破解 acw_sc__v2 challenge...")
        resp = sess.get(f"{BASE_URL}/", timeout=15)
        resp.raise_for_status()

        acw_value = solve_acw_sc_v2(resp.text)
        if not acw_value:
            raise RuntimeError("acw_sc__v2 challenge 破解失败（未找到 arg1）")
        sess.cookies.set("acw_sc__v2", acw_value, domain="anyrouter.top", path="/")
        logger.info(f"✅ challenge 已破解")

        # ── 2. 验证 API 可访问 ──
        status_resp = sess.get(f"{BASE_URL}/api/status", timeout=15)
        try:
            status_data = status_resp.json()
            logger.info(f"✅ API 可访问: success={status_data.get('success')}")
        except json.JSONDecodeError:
            raise RuntimeError("cookie 未生效，API 仍返回 HTML")

        # ── 3. 登录 ──
        logger.info("🔑 登录中...")
        login_resp = sess.post(
            f"{BASE_URL}/api/user/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=15,
        )
        login_data = login_resp.json()

        if not login_data.get("success", False):
            raise RuntimeError(f"登录失败: {login_data.get('message', '未知')}")

        token = login_data.get("data", "")
        if not token:
            raise RuntimeError("登录成功但未返回 token")

        logger.info(f"✅ 登录成功, token: {token[:20]}...")
        logger.info(f"登录响应: {json.dumps(login_data, ensure_ascii=False)[:300]}")
        logger.info(f"登录 set-cookie: {login_resp.headers.get('set-cookie', 'NONE')}")
        sess.headers["Authorization"] = f"Bearer {token}"

        # ── 4. 签到 ──
        logger.info("🎁 签到中...")
        signin_resp = sess.post(f"{BASE_URL}/api/user/sign_in", timeout=15)
        signin_data = signin_resp.json()

        if signin_data.get("success"):
            logger.info(f"🎉 签到成功! {signin_data.get('data', '')}")
        else:
            msg = signin_data.get("message", "")
            logger.info(f"签到返回: {msg}")

        # ── 5. 获取余额 ──
        logger.info("💰 获取余额...")
        user_resp = sess.get(f"{BASE_URL}/api/user/self", timeout=15)
        logger.info(f"余额 API 状态码: {user_resp.status_code}")
        logger.info(f"余额 API 响应: {user_resp.text[:300]}")

        try:
            user_data = user_resp.json()
        except Exception as e:
            logger.error(f"余额响应非 JSON: {e}")
            user_data = {}

        if user_data.get("success"):
            user = user_data.get("data", {})
            result["balance"] = fmt_balance(
                int(user.get("quota", 0)),
                int(user.get("used_quota", 0)),
            )
            logger.info("✅ 余额获取成功")
        else:
            result["balance"] = f"余额获取失败: {user_data.get('message', '未知')}"
            logger.warning(f"余额获取失败: {user_data}")

        result["success"] = True

    except Exception as exc:
        logger.error(f"❌ {exc}")
        result["error"] = str(exc)

    return result


# ════════════════════════════════════════════════════
#  主入口
# ════════════════════════════════════════════════════
def main():
    now_bjt = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"═══ AnyRouter 纯 Python 签到 [{now_bjt} BJT] ═══")

    result = do_checkin()
    now_bjt = datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S")

    if result["success"]:
        msg = (
            f"✅ <b>AnyRouter 每日签到成功</b>\n\n"
            f"🌐 站点: anyrouter.top\n"
            f"👤 用户: <code>{USERNAME}</code>\n"
            f"{result['balance']}\n"
            f"⏰ 时间: {now_bjt} (BJT)\n\n"
            f"<i>🤖 纯协议自动签到</i>"
        )
    else:
        msg = (
            f"❌ <b>AnyRouter 签到失败</b>\n\n"
            f"👤 用户: <code>{USERNAME}</code>\n"
            f"❗ 错误: <code>{result['error']}</code>\n"
            f"⏰ 时间: {now_bjt} (BJT)"
        )

    send_tg(msg)
    logger.info("═══ 签到任务结束 ═══")

    if not result["success"]:
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
