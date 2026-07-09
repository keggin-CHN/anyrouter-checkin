# AnyRouter 自动签到 🤖

[![🔄 AnyRouter 每日自动签到](https://github.com/keggin-CHN/anyrouter-checkin/actions/workflows/checkin.yml/badge.svg)](https://github.com/keggin-CHN/anyrouter-checkin/actions/workflows/checkin.yml)

每天北京时间 **09:00** 自动签到 [anyrouter.top](https://anyrouter.top)，获取余额并推送到 Telegram。

## ✨ 功能

- ✅ 每天 9:00 AM (BJT) 自动签到
- 🔐 纯协议实现 — 破解 `acw_sc__v2` JS challenge，无需 Playwright 浏览器
- 🪶 轻量 — 仅 `requests` + Node.js (challenge solver)
- 🚀 快速 — 整个流程 < 10 秒完成
- 📨 通过 Telegram Bot 推送签到结果
- ❌ 失败时自动发送错误通知

## 🚀 快速开始

### 1. Fork 本仓库

### 2. 配置 GitHub Secrets

进入 `Settings → Secrets and variables → Actions`，添加：

| Secret 名称      | 说明              |
|-----------------|-------------------|
| `AR_USERNAME`   | anyrouter.top 用户名 |
| `AR_PASSWORD`   | anyrouter.top 密码   |
| `TG_BOT_TOKEN`  | Telegram Bot Token   |
| `TG_CHAT_ID`    | Telegram Chat ID     |

### 3. 启用 Actions

进入 `Actions` 页面，点击 `Enable GitHub Actions`

## 🏗️ 技术架构

```
HTTP 请求 anyrouter.top
    ↓
返回 acw_sc__v2 JS challenge (含 arg1)
    ↓
Node.js 子进程执行 challenge JS → 生成 acw_sc__v2 cookie
    ↓
POST /api/user/login {username, password} → Bearer token
    ↓
POST /api/user/sign_in → 签到领配额
    ↓
GET /api/user/self → 查询余额
    ↓
Telegram Bot API → 推送结果
```

**纯协议 = 不需要浏览器引擎 (Playwright/Chromium)，全部通过 HTTP 请求完成。**

## 📩 通知示例

**成功：**
```
✅ AnyRouter 每日签到成功

🌐 站点: anyrouter.top
👤 用户: keggin
💰 剩余: $5.2340
📊 总量: $10.0000 | 已用: $4.7660
⏰ 时间: 2026-07-09 09:00:03 (BJT)
```

**失败：**
```
❌ AnyRouter 签到失败

❗ 错误: 用户名或密码错误
```

## ⚠️ 免责声明

本项目仅供学习和个人使用，请遵守目标网站的使用条款。
