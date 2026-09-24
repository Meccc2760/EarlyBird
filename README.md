# Gradescope 作业提醒

`upgrade/reminder.py` 定时登录 Gradescope，查找尚未提交且未超过截止时间 24 小时的作业，并通过邮件提醒。只要作业仍符合条件，每次运行都会再次提醒；所有作业已提交时不发邮件。

## 用 GitHub Actions 部署

1. Fork 本仓库，在仓库的 `Settings → Secrets and variables → Actions` 添加以下四个 Repository secrets：

   | 名称 | 内容 |
   | --- | --- |
   | `GRADESCOPE_EMAIL` | Gradescope 登录邮箱 |
   | `GRADESCOPE_PASSWORD` | Gradescope 登录密码 |
   | `MAIL_SEND` | 发件邮箱地址 |
   | `MAIL_AUTH_CODE` | 发件邮箱的 SMTP 授权码或应用专用密码，不是 Gradescope 密码 |

   默认将邮件发到 `GRADESCOPE_EMAIL`。如果要发往别的邮箱，再添加可选的 `MAIL_RECEIVE` secret。常见发件邮箱的 SMTP 主机和端口由脚本推断，无需填写。

2. 在 `Actions → Gradescope Scraper` 中手动点击 `Run workflow`，检查本次运行结果。之后工作流按 [scrape.yml](.github/workflows/scrape.yml) 的计划执行；当前时间为北京时间 06:48、13:48、18:48。

工作流执行的是 `python upgrade/reminder.py`。请勿将密码写进代码或提交到仓库。

## 本地运行

如果还没有 `config.json`，先执行 `cp config.example.json config.json` 并填入上述四项。已有配置文件时不要再次复制，以免覆盖原有凭据。安装依赖并运行脚本：

```sh
python -m pip install -r requirements.txt
python upgrade/reminder.py
```

`config.json` 已加入 `.gitignore`。也可以完全使用同名环境变量，不创建文件；环境变量优先于文件。`MAIL_RECEIVE` 可留空，默认使用 Gradescope 邮箱。如果配置文件存放在其他位置，可用 `REMINDER_CONFIG` 环境变量指定路径。

## English quick start

Fork the repository and add four Actions secrets: `GRADESCOPE_EMAIL`, `GRADESCOPE_PASSWORD`, `MAIL_SEND`, and `MAIL_AUTH_CODE` (the sender mailbox's SMTP authorization code or app password). `MAIL_RECEIVE` is optional and defaults to the Gradescope email. Run the **Gradescope Scraper** workflow once manually to check the setup. For local use, copy `config.example.json` to the ignored `config.json` only if you do not already have one, fill in the same fields, and run `python upgrade/reminder.py`.
