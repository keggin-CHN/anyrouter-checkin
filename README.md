# AnyRouter 自动签到 🤖

[![🔄 AnyRouter 每日自动签到](https://github.com/keggin-CHN/anyrouter-checkin/actions/workflows/checkin.yml/badge.svg)](https://github.com/keggin-CHN/anyrouter-checkin/actions/workflows/checkin.yml)

每天北京时间 **09:00** 自动登录 [anyrouter.top](https://anyrouter.top)，获取当前余额并推送到 Telegram。

## ✨ 功能

- ✅ 每天 9:00 AM (BJT) 自动登录
- 💰 登录成功后等待 10 秒，自动抓取余额
- 📨 通过 Telegram Bot 推送签到结果
- 🛡️ 使用 Playwright Chromium 绕过 Cloudflare 防护
- ❌ 失败时自动发送错误通知

## 🚀 快速开始

### 1. Fork 本仓库

点击右上角 Fork 按钮

### 2. 配置 GitHub Secrets

进入 `Settings → Secrets and variables → Actions`，添加以下 Secrets：

| Secret 名称      | 说明              |
|-----------------|-------------------|
| `AR_USERNAME`   | anyrouter.top 用户名 |
| `AR_PASSWORD`   | anyrouter.top 密码   |
| `TG_BOT_TOKEN`  | Telegram Bot Token   |
| `TG_CHAT_ID`    | Telegram Chat ID     |

### 3. 启用 Actions

进入 `Actions` 页面，点击 `Enable GitHub Actions`

## 🗓️ 运行计划

| 时间表        | 说明                 |
|--------------|----------------------|
| 每天 01:00 UTC | 北京时间 09:00 (BJT)  |

也可手动触发: `Actions → 🔄 AnyRouter 每日自动签到 → Run workflow`

## 📩 通知示例

**成功时：**
```
✅ AnyRouter 每日签到成功

🌐 站点: anyrouter.top
👤 用户: keggin
💰 剩余: $5.2340
📊 总量: $10.0000 | 已用: $4.7660
⏰ 时间: 2026-06-21 09:00:12 (BJT)
```

**失败时：**
```
❌ AnyRouter 签到失败

🌐 站点: anyrouter.top
👤 用户: keggin
❗ 错误: 未找到用户名输入框
⏰ 时间: 2026-06-21 09:00:08 (BJT)
```

## 🔧 技术栈

- Python 3.11
- [Playwright](https://playwright.dev/python/) - 浏览器自动化
- GitHub Actions - 定时调度
- Telegram Bot API - 消息推送

## ⚠️ 免责声明

本项目仅供学习和个人使用，请遵守目标网站的使用条款。
