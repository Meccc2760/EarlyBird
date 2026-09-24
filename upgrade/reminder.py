import os
import smtplib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        retry_strategy = Retry(
            total = 3,
            backoff_factor = 1,
            status_forcelist = [429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries = retry_strategy)

        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @abstractmethod
    def login(self, username: str, password: str) -> bool:
        """执行登录操作。成功返回 True，失败返回 False。"""
        pass

    @abstractmethod
    def fetch_unsubmitted_assignments(self) -> List[Assignment]:
        """获取该平台下所有符合提醒条件的未提交作业。"""
        pass

class GradescopeScraper(PlatformScraper):
    """
    Gradescope 的具体爬虫实现。
    """
    BASE_URL = "https://www.gradescope.com"
    LOGIN_URL = f"{BASE_URL}/login"
    ACCOUNT_URL = f"{BASE_URL}/account"

    def login(self, email: str, password: str) -> bool:
        print("[Gradescope] 正在登录...")
        # TODO: 将原代码中的 login_to_gradescope 逻辑搬过来
        # 使用 self.session
        # 如果登录成功 return True，否则 return False
        try:
            get_response = self.session.get(self.LOGIN_URL)
        except Exception as e:
            print(f"访问登录页面失败: {e}")
            return False
        
        soup = BeautifulSoup(get_response.text, "html.parser")
        
        if not (token_element := soup.select_one('meta[name="csrf-token"]')):
            print("获取登陆令牌失败。")
            return False
        auth_token = token_element.get("content")

        payload = {
            "session[email]": email,
            "session[password]": password,
            "authenticity_token": auth_token,
            "commit": "Log In"
        }

        print("...正在提交登陆信息")
        try:
            post_response = self.session.post(self.LOGIN_URL, data = payload)
        except Exception as e:
            print(f"登录失败: {e}")
            return False
        
        successful_urls = [f"{self.BASE_URL}/account", f"{self.BASE_URL}/courses"]
        if post_response.url in successful_urls:
            print("登录成功！")
            return True
        else:
            print("登录失败，请检查账号或密码。")
            print(f"提示：登录后页面停留在 {post_response.url}")
            return False

    def fetch_unsubmitted_assignments(self) -> List[Assignment]:
        print("[Gradescope] 正在抓取未交作业...")      
        # TODO: 
        # 1. 调用 get_courses 逻辑获取课程列表
        # 2. 遍历课程，调用 get_assignments 逻辑，解析表格，比对 24 小时过期时间
        # 3. 将解析出来的结果实例化为 Assignment 对象并 append 到 assignments 列表中
        # 提示：在这里执行原来复杂的 datetime 逻辑，判断 is_too_late。
        try:
            get_response = self.session.get(self.ACCOUNT_URL)
        except Exception as e:
            print(f"获取账户主页失败: {e}")
            return []
        assignments: List[Assignment] = []

        soup = BeautifulSoup(get_response.text, "html.parser")
        term_tags = soup.select(".courseList")
        for terms in term_tags:
            term_tag = terms.select_one(".courseList--term")
            term = term_tag.get_text(strip = True) if term_tag else "Unknown Term"
            course_tags = terms.select("a.courseBox[href^='/courses/']")
            for course in course_tags:
                name_tag = course.find("div", class_="courseBox--name")
                name = name_tag.get_text(strip = True) if name_tag else course.get_text(strip = True)
                href = course.get("href")

                full_name = f"{name} - {term}"
                url = f"{self.BASE_URL}{href}"

                course_assignment = self._fetch_assignments_for_course(full_name, url)
                assignments.extend(course_assignment)
                time.sleep(0.1)

        return assignments

    def _fetch_assignments_for_course(self, name, url) -> List[Assignment]:
        try:
            get_response = self.session.get(url)
        except Exception as e:
            print(f"查找课程主页失败: {e}")
            return []
        unsubmitted_assignments = []
        
        soup = BeautifulSoup(get_response.text, "html.parser")
        if not (table_body := soup.select_one("table#assignments-student-table tbody")):
            return unsubmitted_assignments
        
        assignment_rows = list(table_body.find_all("tr", recursive = False))
        now = datetime.now(timezone.utc)

        for row in assignment_rows:
            if not isinstance(row, Tag):
                continue

            name_th = row.find("th", scope="row")
            if not name_th: 
                continue
            assign_name = name_th.get_text(strip=True)

            all_tds = row.find_all("td")
            if not all_tds: 
                continue
            status_text = all_tds[0].get_text(strip=True)
            if "No Submission" not in status_text:
                continue

            link_a = name_th.find("a")
            href = link_a.get("href") if link_a else None
            assign_link = f"{self.BASE_URL}{href}" if isinstance(href, str) else url

            due_date_text = "N/A"
            is_too_late = False
            max_due_dt = None 
            
            time_tags = row.find_all("time", class_="submissionTimeChart--dueDate")
            parsed_dates = []
            
            for t in time_tags:
                if isinstance(dt_str := t.get("datetime"), str):
                    try:
                        s = dt_str.strip().replace(" ", "T", 1).replace(" ", "")
                        if "+" in s and s[-3] != ":":
                            s = f"{s[:-2]}:{s[-2:]}"
                        
                        parsed_dt = datetime.fromisoformat(s)
                        parsed_dates.append({
                            "dt": parsed_dt,
                            "text": t.get_text(strip=True)
                        })
                        
                    except Exception as e:
                        print(f"    [警告] 解析日期失败 '{dt_str}': {e}")

            if parsed_dates:
                latest_info = max(parsed_dates, key=lambda x: x["dt"])
                max_due_dt = latest_info["dt"]
                due_date_text = latest_info["text"]

                if len(parsed_dates) > 1:
                    due_date_text += " (含 Late)"

                if now > (max_due_dt + timedelta(hours=24)):
                    is_too_late = True

            if not is_too_late:
                assignment_obj = Assignment(
                    platform_name = "Gradescope",
                    course_name = name, 
                    assignment_name = assign_name,
                    status = status_text,
                    due_date_str = due_date_text,
                    due_date_dt = max_due_dt,
                    url = assign_link
                )
                unsubmitted_assignments.append(assignment_obj)

        return unsubmitted_assignments
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
        "foxmail.com": ("smtp.qq.com", 465, True),
        "gmail.com": ("smtp.gmail.com", 465, True),
        "outlook.com": ("smtp.office365.com", 587, False), # 587 通常用 STARTTLS
        "163.com": ("smtp.163.com", 465, True),
    }

    def __init__(self, sender_email: str, sender_password: str, receiver_email: str):
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.receiver_email = receiver_email

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
            lines.append(f"   状态: {a.status}")
            lines.append(f"   截止: {a.due_date_str}")
            lines.append(f"   链接: {a.url}")
            lines.append("-" * 20)
        body = "\n".join(lines)

        subject = f"[{assignments[0].platform_name}] 发现未交作业 {len(assignments)} 项"

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
    """
    # 1. 读取凭证配置
    gs_email = os.getenv("GRADESCOPE_EMAIL")
    gs_password = os.getenv("GRADESCOPE_PASSWORD")
    
    # 优化后的邮件配置，只需邮箱和密码
    mail_send = os.getenv("MAIL_SEND")       
    mail_authcode = os.getenv("MAIL_PASSWORD")
    mail_receive = os.getenv("MAIL_RECEIVE")

    if not mail_receive:
        mail_receive = mail_send
        print("未填写收件邮箱，默认使用发件邮箱作为收件邮箱。")
    if not all([gs_email, gs_password]):
        print("错误: 缺少 Gradescope 登录凭证。")
        return
    """
    # TODO: clear local accounts
    gs_email = "chensh2025@shanghaitech.edu.cn"
    gs_password = "320105200704223412"
    mail_send = "1123562283@qq.com"
    mail_authcode = "htfbrhiedzapijja"
    mail_receive = "chensh2025@shanghaitech.edu.cn"

    # 2. 组装我们要运行的爬虫列表 (现在只有 GS，未来可以 append 其他平台)
    scrapers: List[PlatformScraper] = []
    
    gs_scraper = GradescopeScraper()
    if gs_scraper.login(gs_email, gs_password):
        scrapers.append(gs_scraper)
    else:
        print("GradeScope登陆失败。")
        return
    
    # 3. 收集所有平台的未交作业
    all_unsubmitted: List[Assignment] = []
    for scraper in scrapers:
        all_unsubmitted.extend(scraper.fetch_unsubmitted_assignments())

    # 4. 组装我们要触发的通知器列表
    notifiers: List[BaseNotifier] = []
    
    if mail_send and mail_authcode and mail_receive:
        try:
            notifiers.append(EmailNotifier(sender_email = mail_send, sender_password = mail_authcode, receiver_email = mail_receive))
        except Exception as e:
            print(f"邮件发送失败: {e}")
    # 留出以后加 QQ 的口子：
    # if os.getenv("QMSG_KEY"):
    #     notifiers.append(QmsgNotifier(os.getenv("QMSG_KEY")))

    # 5. 广播通知
    if not all_unsubmitted:
        print("\n所有平台的作业都已完成！")
    else:
        print(f"\n--- 汇总结果：共 {len(all_unsubmitted)} 项未交作业 ---")
        for notifier in notifiers:
            notifier.send(all_unsubmitted)

if __name__ == "__main__":
    main()