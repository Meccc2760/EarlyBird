# Early Bird Reminder

Early Bird avoids DDLs. 这个脚本会定期自动访问你的Gradescope账号，并整理汇总所有未提交的作业，然后发邮件提醒你。

值得注意的是，只要存在未过期的unsubmitted assignment，脚本就会在每次auto run的时候给你发邮件。也就是说，一旦assignment released，只要你没有完成并submit，就会一直收到催命提醒邮件。在无穷无尽的骚扰下，你终于决定尽早完成assignment以免受骚扰。

因此，这个脚本适用于习惯及时处理assignment的使用者，或者希望尽早获知assignment release的使用者，又或者是决心不再当ddl战士的使用者，它可以起到一个提醒和激励的作用。但它并不适合习惯于临近ddl才完成assignment的使用者，显然你会每天收到很多封提醒邮件。请诸位按需使用。

> 可以在`workflow/scrape.yml`中修改发信时间和频率。

## 用 GitHub Actions 部署

1. Fork 本仓库。在你自己的仓库中打开 **Actions**，按页面提示启用工作流。GitHub 默认会禁用公开仓库 fork 中的定时工作流，因此请确认 **Gradescope Scraper** 处于启用状态。
2. 打开 **Settings → Secrets and variables → Actions → Repository secrets**，添加下面四项：

   | 名称 | 填写内容 |
   | --- | --- |
   | `GRADESCOPE_EMAIL` | Gradescope 登录邮箱 |
   | `GRADESCOPE_PASSWORD` | Gradescope 登录密码 |
   | `MAIL_SEND` | 用来发送提醒的邮箱地址 |
   | `MAIL_AUTH_CODE` | 发件邮箱的 SMTP 登录凭据，通常是客户端授权码或应用专用密码；不是 Gradescope 密码 |

   收件邮箱默认是 `GRADESCOPE_EMAIL`。如果想发到其他地址，再添加可选的 `MAIL_RECEIVE` secret；收件邮箱不需要开启 SMTP。

   > 发件邮箱需要允许第三方通过 SMTP 登录。QQ、Foxmail、163 邮箱可在邮箱设置中开启相应服务并取得授权码；Gmail 需要能够创建应用专用密码。Outlook.com、Hotmail.com 和 Live.com 当前不能用作发件邮箱。学校或公司邮箱是否能发信取决于管理员设置，本项目不保证支持；它们仍可作为收件邮箱。

3. 在 **Actions → Gradescope Scraper → Run workflow** 手动运行一次。日志应显示登录成功、选中的学期和检查的课程数。（若没有未交作业，运行成功也不会发邮件）

之后的工作流在北京时间每天 **06:55、12:55、17:55** 自动运行。要改时间，编辑 [scrape.yml](.github/workflows/scrape.yml) 中的 `schedule`。GitHub 的定时任务可能稍有延迟。

## 本地运行

在仓库根目录创建 `config.json`（如果已经有了，不必重建）：

```json
{
  "GRADESCOPE_EMAIL": "your.name@school.edu",
  "GRADESCOPE_PASSWORD": "your-gradescope-password",
  "MAIL_SEND": "sender@qq.com",
  "MAIL_AUTH_CODE": "your-smtp-auth-code"
}
```

在 macOS 或 Linux 上安装依赖并运行：

```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python reminder.py
```

`config.json` 已被 Git 忽略。你也可以使用同名环境变量，不创建文件；环境变量优先于文件。`MAIL_RECEIVE` 留空时默认使用 Gradescope 邮箱，`REMINDER_CONFIG` 可用于指定其他配置文件路径。

## English quick start

Fork this repository, enable the workflow in **Actions**, and add four repository secrets: `GRADESCOPE_EMAIL`, `GRADESCOPE_PASSWORD`, `MAIL_SEND`, and `MAIL_AUTH_CODE` (the sender mailbox's SMTP credential, usually an app password). `MAIL_RECEIVE` is optional and defaults to the Gradescope email. Run **Gradescope Scraper** manually once; it checks only the newest term. Scheduled runs occur at 06:55, 12:55, and 17:55 in `Asia/Shanghai`. For local use, create an ignored `config.json` with the same fields and run `venv/bin/python reminder.py` after installing dependencies.
