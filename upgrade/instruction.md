这是一份为你量身定制的重构指南！我非常理解你希望重构代码的初衷：随着功能的增加（支持更多网站、支持更多通知方式），原本写在单个脚本里的面向过程代码会变得臃肿且难以维护。

我仔细阅读了你提供的《CS100 HW8》指导文档。那是一份非常优秀的 C++ 游戏开发作业说明，其核心思想是**面向对象编程（OOP）**和**模块化设计**。

为了让你有如同“完成一份精心设计的计科大作业”的体验，我完全**仿照了那份文档的行文风格、排版逻辑和 OOP 思想**，为你编写了这篇《作业管家重构指南 (Instructor)》。在指南之后，我会提供一份搭建好骨架的代码框架。

---

# 作业管家 (Homework Manager) 重构概览

## 注意事项
*   **请为本次重构分配充足的时间**，不要急于把旧代码直接复制粘贴过来。理解整个架构后再动笔！
*   本次重构的核心目标是**解耦**（Decoupling）。爬虫不该管怎么发邮件，通知器也不该管怎么解析网页。
*   如果对任何部分有疑问，请先思考面向对象的原则：这个方法应该属于哪个类？这个变量是私有还是公开的？
*   **请一定经常保存备份**（推荐使用 Git）。重构时常会遇到“牵一发而动全身”的 bug，良好的版本控制能救你一命。

## 目录
1. [故事与背景](#1)
2. [架构是如何运作的](#2)
3. [从数据结构开始：Assignment 类](#3)
4. [爬虫基类与 Gradescope 派生类](#4)
5. [通知器基类与智能邮件通知器](#5)
6. [好的，所以这么多东西我怎么写？](#6)

---

<h2 id="1">1. 故事与背景</h2>

### 1.1 项目简介
你所要重构的这款软件是一个自动化作业提醒工具。在这个工具中，程序代替你登录各大教学平台，检索未完成的作业，并在临近截止日期时通过不同渠道向你发出警报。

### 1.2 你要做什么
你会拿到一份**代码框架**，框架为你定义好了各种“基类（Base Classes）”以及主程序的运行流程，但没有具体的业务逻辑。你需要通过代码填充各个类的功能。
这次重构的要求是：**模块化与可扩展性**。你现在可能只需要 Gradescope 和 Email，但你的架构必须允许明天只需写极少的代码就能加入 Blackboard 爬虫或 QQBot 通知器。

<h2 id="2">2. 架构是如何运作的</h2>

面向对象编程（OOP）的思想在复杂脚本中被广泛应用。我们可以将这个脚本的所有组成成分抽象成一个个独立的对象。

刚刚提到过，我们要为未来留下扩展接口。因此，我们不能再写一个名为 `get_assignments()` 的孤立函数了。我们要设计一个基类叫做 `PlatformScraper`（平台爬虫），它规定了所有的爬虫都必须能返回一个作业列表。然后，我们让 `GradescopeScraper` 去继承它，并实现具体的爬取逻辑。

同样地，对于通知渠道，我们设计一个基类叫做 `Notifier`（通知器）。无论是邮件、QQ 还是微信，它们都属于通知器，它们都必须实现一个 `send()` 方法。主程序不需要知道当前用的是邮件还是 QQ，它只需要调用 `notifier.send(assignments)`，这就是**多态（Polymorphism）**的魅力。

<h2 id="3">3. 从数据结构开始：Assignment 类</h2>

在原代码中，你使用 `dict` 字典来传递作业信息 (`{"name": "...", "due_date": "..."}`)。
虽然字典很灵活，但极易拼错键名（比如把 `due_date` 写成 `due`），导致运行时崩溃。

在新的架构中，所有爬虫的最终输出，以及所有通知器的输入，都必须是一个统一的数据结构。在 Python 中，我们强烈推荐使用 `@dataclass` 来定义 `Assignment`。它就像 C++ 里的 `struct`，规范了我们到底应当存什么，不应当存什么。

<h2 id="4">4. 爬虫基类与 Gradescope 派生类</h2>

你的 `PlatformScraper` 类是一个**抽象基类**（相当于 C++ 里的纯虚类）。它定义了规范，但不做具体的事情：

```python
class PlatformScraper(ABC):
    @abstractmethod
    def login(self) -> bool:
        pass
        
    @abstractmethod
    def fetch_unsubmitted_assignments(self) -> list[Assignment]:
        pass
```

之后，你的 `GradescopeScraper` 将继承这个基类。在它自己的实现中，你可以保留原来的 `session`、`requests` 以及漂亮的 `BeautifulSoup` 解析逻辑。

<h2 id="5">5. 通知器基类与智能邮件通知器</h2>

通知器同样需要一个基类 `BaseNotifier`，其中包含一个纯虚函数 `notify(assignments: list[Assignment])`。

针对你提出的**“尽量简化收件过程（不用用户填写太多 smtp 等东西，尽量只用填一个邮箱）”**，我们可以在 `EmailNotifier` 类中实现一个**智能解析机制**：
用户只需提供 `sender_email` 和 `sender_password`。类在初始化时，会提取邮箱后缀（如 `@qq.com`, `@gmail.com`），并通过一个预设的字典（Mapping）自动查找对应的 SMTP 服务器地址和端口。这样就完美隐藏了复杂的配置！

<h2 id="6">6. 好的，所以这么多东西我怎么写？</h2>

可想而知，从零重构一个架构良好的程序绝不是一蹴而就的。我们建议你按以下流程逐步进行：

1.  **定义数据类**：先写出 `Assignment` 的 DataClass。
2.  **实现邮件通知器**：先不管爬虫，写出 `EmailNotifier` 类，自己手动 `[Assignment(name="测试")]` 喂给它，看看能不能成功发出邮件。这部分最容易获得正反馈。
3.  **实现 Gradescope 爬虫**：把以前抓取和筛选时间（24小时过滤）的逻辑搬进 `GradescopeScraper` 的方法中。
4.  **组装游戏世界（Main Loop）**：在 `main()` 函数中，实例化你的爬虫和通知器，将它们连结起来。

---
<br>

# 代码框架 (Code Framework)

下面是为你准备的 Python 代码框架。我已使用了 `abc` 模块（Abstract Base Classes）来构建基类，并为你搭好了所有的结构。请仔细阅读注释，在 `# TODO:` 的地方填入你原有的或新的逻辑。

```python
import os
import smtplib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

# ==========================================
# 1. 统一的数据结构 (Data Structures)
# ==========================================

@dataclass
class Assignment:
    """
    统一的作业数据结构。
    无论是 Gradescope 还是未来的 Blackboard，爬取结果都必须转换为此对象。
    """
    platform_name: str    # 平台名称，例如 "Gradescope"
    course_name: str      # 课程名称
    assignment_name: str  # 作业名称
    status: str           # 当前状态，例如 "No Submission"
    due_date_str: str     # 用于展示的截止时间字符串
    due_date_dt: Optional[datetime] # 真实的 datetime 对象，方便后续过滤
    url: str              # 作业或课程链接

# ==========================================
# 2. 爬虫基类与实现 (Scraper Classes)
# ==========================================

class PlatformScraper(ABC):
    """
    抽象基类：所有平台爬虫必须继承此基类并实现以下方法。
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
        })

    @abstractmethod
    def login(self, username: str, password: str) -> bool:
        """执行登录操作。成功返回 True，失败返回 False。"""
        pass

    @abstractmethod
    def fetch_unsubmitted_assignments(self) -> List[Assignment]:
        """获取该平台下所有符合提醒条件的未提交作业。"""
        pass

    # 你可以把之前的 safe_request 作为一个 protected 方法放进基类，供所有爬虫使用
    def _safe_request(self, method: str, url: str, retries: int = 2, **kwargs) -> Optional[requests.Response]:
        # TODO: 将原代码中的 safe_request 逻辑复制到这里
        pass


class GradescopeScraper(PlatformScraper):
    """
    Gradescope 的具体爬虫实现。
    """
    BASE_URL = "https://www.gradescope.com"
    LOGIN_URL = f"{BASE_URL}/login"

    def login(self, username: str, password: str) -> bool:
        print("[Gradescope] 正在登录...")
        # TODO: 将原代码中的 login_to_gradescope 逻辑搬过来
        # 使用 self._safe_request 和 self.session
        # 如果登录成功 return True，否则 return False
        return True

    def fetch_unsubmitted_assignments(self) -> List[Assignment]:
        print("[Gradescope] 正在抓取未交作业...")
        assignments: List[Assignment] = []
        # TODO: 
        # 1. 调用 get_courses 逻辑获取课程列表
        # 2. 遍历课程，调用 get_assignments 逻辑，解析表格，比对 24 小时过期时间
        # 3. 将解析出来的结果实例化为 Assignment 对象并 append 到 assignments 列表中
        # 提示：在这里执行原来复杂的 datetime 逻辑，判断 is_too_late。
        return assignments

# 如果未来要加 Blackboard，只需要写一个 BlackboardScraper(PlatformScraper) 即可。


# ==========================================
# 3. 通知器基类与实现 (Notifier Classes)
# ==========================================

class BaseNotifier(ABC):
    """
    抽象基类：所有通知方式必须继承此基类。
    """
    @abstractmethod
    def send(self, assignments: List[Assignment]) -> bool:
        """发送通知。成功返回 True，失败返回 False。"""
        pass


class EmailNotifier(BaseNotifier):
    """
    智能邮件通知器：只需提供发件邮箱和授权码，自动推断 SMTP 配置。
    """
    # 常用邮箱的 SMTP 配置映射表 (SMTP_HOST, PORT, USE_SSL)
    SMTP_CONFIG_MAP = {
        "qq.com": ("smtp.qq.com", 465, True),
        "gmail.com": ("smtp.gmail.com", 465, True),
        "outlook.com": ("smtp.office365.com", 587, False), # 587 通常用 STARTTLS
        "163.com": ("smtp.163.com", 465, True),
    }

    def __init__(self, sender_email: str, sender_password: str, receiver_email: Optional[str] = None):
        self.sender_email = sender_email
        self.sender_password = sender_password
        # 如果没有专门指定收件人，就发给自己
        self.receiver_email = receiver_email if receiver_email else sender_email

    def _guess_smtp_config(self):
        """根据邮箱后缀推断服务器配置。"""
        domain = self.sender_email.split('@')[-1].lower()
        if domain in self.SMTP_CONFIG_MAP:
            return self.SMTP_CONFIG_MAP[domain]
        else:
            print(f"[警告] 未知邮箱后缀 @{domain}，默认尝试使用 smtp.{domain}，端口 465")
            return (f"smtp.{domain}", 465, True)

    def send(self, assignments: List[Assignment]) -> bool:
        if not assignments:
            print("没有需要通知的作业。")
            return True

        host, port, use_ssl = self._guess_smtp_config()
        
        # TODO: 使用统一的 Assignment 对象来组装邮件正文
        lines = [f"共发现未提交作业 {len(assignments)} 项：\n"]
        for i, a in enumerate(assignments, start=1):
            lines.append(f"{i}. [{a.platform_name}] {a.course_name}")
            lines.append(f"   作业: {a.assignment_name}")
            lines.append(f"   截止: {a.due_date_str}")
            lines.append("-" * 20)
        body = "\n".join(lines)

        subject = f"[作业管家] 发现未交作业 {len(assignments)} 项"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = self.receiver_email
        msg.set_content(body)

        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                server.starttls()
            
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()
            print(f"邮件已成功发送至 {self.receiver_email}")
            return True
        except Exception as e:
            print(f"邮件发送失败: {e}")
            return False


class QmsgNotifier(BaseNotifier):
    """
    Qmsg酱 QQ通知器 (已搭好框架，暂时无需实现具体逻辑，留作未来扩展)
    """
    def __init__(self, qmsg_key: str):
        self.qmsg_key = qmsg_key

    def send(self, assignments: List[Assignment]) -> bool:
        if not self.qmsg_key:
            return False
        # TODO: 未来在此粘贴你的 Qmsg post 请求逻辑
        print("[QmsgNotifier] Qmsg 通知尚未实现。")
        return True


# ==========================================
# 4. 主程序 (Main Execution Loop)
# ==========================================

def main():
    # 1. 读取凭证配置
    gs_email = os.getenv("GRADESCOPE_EMAIL")
    gs_password = os.getenv("GRADESCOPE_PASSWORD")
    
    # 优化后的邮件配置，只需邮箱和密码
    mail_user = os.getenv("MAIL_USER")       
    mail_password = os.getenv("MAIL_PASSWORD")

    if not all([gs_email, gs_password]):
        print("错误: 缺少 Gradescope 登录凭证。")
        return

    # 2. 组装我们要运行的爬虫列表 (现在只有 GS，未来可以 append 其他平台)
    scrapers: List[PlatformScraper] = []
    
    gs_scraper = GradescopeScraper()
    if gs_scraper.login(gs_email, gs_password):
        scrapers.append(gs_scraper)

    # 3. 收集所有平台的未交作业
    all_unsubmitted: List[Assignment] = []
    for scraper in scrapers:
        all_unsubmitted.extend(scraper.fetch_unsubmitted_assignments())

    # 4. 组装我们要触发的通知器列表
    notifiers: List[BaseNotifier] = []
    
    if mail_user and mail_password:
        notifiers.append(EmailNotifier(sender_email=mail_user, sender_password=mail_password))
    # 留出以后加 QQ 的口子：
    # if os.getenv("QMSG_KEY"):
    #     notifiers.append(QmsgNotifier(os.getenv("QMSG_KEY")))

    # 5. 广播通知
    if not all_unsubmitted:
        print("\n太棒了，所有平台的作业都已完成！")
    else:
        print(f"\n--- 汇总结果：共 {len(all_unsubmitted)} 项未交作业 ---")
        for notifier in notifiers:
            notifier.send(all_unsubmitted)

if __name__ == "__main__":
    main()
```

你可以按照《重构指南》里的建议，从上到下将你原来的逻辑分门别类地填入其中。如果填坑的过程中遇到任何 Bug 或不知道该用什么姿势放置代码，随时问我！