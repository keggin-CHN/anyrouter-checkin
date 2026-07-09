# AnyRouter 自动签到 🤖

[![🔄 AnyRouter 每日自动签到](https://github.com/keggin-CHN/anyrouter-checkin/actions/workflows/checkin.yml/badge.svg)](https://github.com/keggin-CHN/anyrouter-checkin/actions/workflows/checkin.yml)

每天北京时间 **09:00** 自动签到 [anyrouter.top](https://anyrouter.top)，获取余额并推送到 Telegram。

## ✨ 功能

- ✅ 每天 9:00 AM (BJT) 自动签到
- 🔐 **纯 Python** 实现 `acw_sc__v2` challenge 破解
- 🪶 单文件，仅依赖 `requests`，无 Playwright / Node.js / 第三方服务
- 🚀 整个流程 < 10 秒
- 📨 Telegram Bot 推送签到结果

## 🚀 快速开始

### 1. Fork 本仓库

### 2. 配置 GitHub Secrets

`Settings → Secrets and variables → Actions`：

| Secret           | 说明                    |
|-----------------|------------------------|
| `AR_USERNAME`   | anyrouter.top 用户名    |
| `AR_PASSWORD`   | anyrouter.top 密码      |
| `TG_BOT_TOKEN`  | Telegram Bot Token      |
| `TG_CHAT_ID`    | Telegram Chat ID        |

### 3. 启用 Actions

## 🏗️ 技术架构

```
GET anyrouter.top → 返回 acw_sc__v2 JS challenge (含 arg1)
    ↓
纯 Python: 置换表重排 arg1 → XOR 固定 key → acw_sc__v2 cookie
    ↓
POST /api/user/login → Bearer token
    ↓
POST /api/user/sign_in → 签到
    ↓
GET /api/user/self → 余额
    ↓
Telegram 推送
```

无浏览器引擎，无打码服务，纯 HTTP 协议。

## ⚠️ 免责声明

本项目仅供学习和个人使用，请遵守目标网站的使用条款。
