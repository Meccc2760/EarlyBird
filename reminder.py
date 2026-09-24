import json
import os
import smtplib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Mapping

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class ReminderConfig:
    gradescope_email: str
    gradescope_password: str
    sender_email: str
    sender_auth_code: str
    receiver_email: str

    @classmethod
    def Load(cls, environ: Mapping[str, str] | None = None) -> "ReminderConfig":
        """Read environment variables first, then the optional local config file."""
        env = os.environ if environ is None else environ
        custom_path = env.get("REMINDER_CONFIG", "").strip()
        config_path = Path(custom_path) if custom_path else Path(__file__).resolve().parent.parent / "config.json"
        file_config = {}

        if custom_path or config_path.exists():
            try:
                file_config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"无法读取配置文件 {config_path}: {exc}") from exc
            if not isinstance(file_config, dict):
                raise ValueError(f"配置文件 {config_path} 必须是 JSON 对象")

        def ReadValue(name: str) -> str:
            raw_value = env.get(name) or file_config.get(name, "")
            return raw_value.strip() if isinstance(raw_value, str) else ""

        required_fields = ("GRADESCOPE_EMAIL", "GRADESCOPE_PASSWORD", "MAIL_SEND", "MAIL_AUTH_CODE")
        missing_fields = [name for name in required_fields if not ReadValue(name)]
        if missing_fields:
            raise ValueError("缺少配置项: " + ", ".join(missing_fields))

        return cls(
            gradescope_email=ReadValue("GRADESCOPE_EMAIL"),
            gradescope_password=ReadValue("GRADESCOPE_PASSWORD"),
            sender_email=ReadValue("MAIL_SEND"),
            sender_auth_code=ReadValue("MAIL_AUTH_CODE"),
            receiver_email=ReadValue("MAIL_RECEIVE") or ReadValue("GRADESCOPE_EMAIL"),
        )


@dataclass
class Assignment:
    """A submission to remind about; due_date_dt is used for filtering."""

    platform_name: str
    course_name: str
    assignment_name: str
    status: str
    due_date_str: str  # Text shown in the email.
    due_date_dt: datetime | None  # Parsed deadline; unused by the current notifier.
    url: str


class PlatformScraper(ABC):
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
        })
        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @abstractmethod
    def Login(self, username: str, password: str) -> bool:
        pass

    @abstractmethod
    def FetchUnsubmittedAssignments(self) -> list[Assignment]:
        pass


class GradescopeScraper(PlatformScraper):
    base_url = "https://www.gradescope.com"
    login_url = f"{base_url}/login"
    account_url = f"{base_url}/account"

    def Login(self, email: str, password: str) -> bool:
        print("[Gradescope] 正在登录...")
        # TODO: Recheck this redirect check if Gradescope changes its login flow.
        try:
            response = self.session.get(self.login_url)
        except requests.RequestException as exc:
            print(f"访问登录页面失败: {exc}")
            return False

        soup = BeautifulSoup(response.text, "html.parser")
        token_element = soup.select_one('meta[name="csrf-token"]')
        if token_element is None or not token_element.get("content"):
            print("获取登录令牌失败。")
            return False

        payload = {
            "session[email]": email,
            "session[password]": password,
            "authenticity_token": token_element["content"],
            "commit": "Log In",
        }

        try:
            response = self.session.post(self.login_url, data=payload)
        except requests.RequestException as exc:
            print(f"登录失败: {exc}")
            return False

        if response.url in (self.account_url, f"{self.base_url}/courses"):
            print("登录成功！")
            return True

        print("登录失败，请检查账号或密码。")
        print(f"提示：登录后页面停留在 {response.url}")
        return False

    def FetchUnsubmittedAssignments(self) -> list[Assignment]:
        print("[Gradescope] 正在抓取未交作业...")
        # TODO: Recheck course selectors when Gradescope changes its HTML.
        try:
            response = self.session.get(self.account_url)
        except requests.RequestException as exc:
            print(f"获取账户主页失败: {exc}")
            return []

        assignments = []
        soup = BeautifulSoup(response.text, "html.parser")
        for course_list in soup.select(".courseList"):
            term_tag = course_list.select_one(".courseList--term")
            term = term_tag.get_text(strip=True) if term_tag else "Unknown Term"
            for course_tag in course_list.select("a.courseBox[href^='/courses/']"):
                name_tag = course_tag.find("div", class_="courseBox--name")
                course_name = name_tag.get_text(strip=True) if name_tag else course_tag.get_text(strip=True)
                course_url = f"{self.base_url}{course_tag.get('href')}"
                assignments.extend(self.FetchAssignmentsForCourse(f"{course_name} - {term}", course_url))
                time.sleep(0.1)

        return assignments

    def FetchAssignmentsForCourse(self, course_name: str, course_url: str) -> list[Assignment]:
        # TODO: Recheck assignment and deadline selectors when Gradescope changes its HTML.
        try:
            response = self.session.get(course_url)
        except requests.RequestException as exc:
            print(f"查找课程主页失败: {exc}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        table_body = soup.select_one("table#assignments-student-table tbody")
        if table_body is None:
            return []

        unsubmitted_assignments = []
        now = datetime.now(timezone.utc)
        for row in table_body.find_all("tr", recursive=False):
            name_tag = row.find("th", scope="row")
            if name_tag is None:
                continue

            cells = row.find_all("td")
            if not cells:
                continue
            status_text = cells[0].get_text(strip=True)
            if "No Submission" not in status_text:
                continue

            link_tag = name_tag.find("a")
            href = link_tag.get("href") if link_tag else None
            assignment_url = f"{self.base_url}{href}" if isinstance(href, str) else course_url
            due_date_text = "N/A"
            latest_due_date = None
            parsed_dates = []

            for time_tag in row.find_all("time", class_="submissionTimeChart--dueDate"):
                date_string = time_tag.get("datetime")
                if not isinstance(date_string, str):
                    continue
                try:
                    normalized_date = date_string.strip().replace(" ", "T", 1).replace(" ", "")
                    if "+" in normalized_date and normalized_date[-3] != ":":
                        normalized_date = f"{normalized_date[:-2]}:{normalized_date[-2:]}"
                    parsed_dates.append((datetime.fromisoformat(normalized_date), time_tag.get_text(strip=True)))
                except ValueError as exc:
                    print(f"    [警告] 解析日期失败 '{date_string}': {exc}")

            if parsed_dates:
                # Gradescope may show both regular and late deadlines; use the latest one.
                latest_due_date, due_date_text = max(parsed_dates, key=lambda item: item[0])
                if len(parsed_dates) > 1:
                    due_date_text += " (含 Late)"
                if now > latest_due_date + timedelta(hours=24):
                    continue

            unsubmitted_assignments.append(Assignment(
                platform_name="Gradescope",
                course_name=course_name,
                assignment_name=name_tag.get_text(strip=True),
                status=status_text,
                due_date_str=due_date_text,
                due_date_dt=latest_due_date,
                url=assignment_url,
            ))

        return unsubmitted_assignments


class BaseNotifier(ABC):
    @abstractmethod
    def Send(self, assignments: list[Assignment]) -> bool:
        pass


class EmailNotifier(BaseNotifier):
    """Send mail using SMTP settings inferred from the sender's domain."""

    smtp_config_map = {
        "qq.com": ("smtp.qq.com", 465, True),
        "foxmail.com": ("smtp.qq.com", 465, True),
        "gmail.com": ("smtp.gmail.com", 465, True),
        "outlook.com": ("smtp.office365.com", 587, False),
        "163.com": ("smtp.163.com", 465, True),
    }

    def __init__(self, sender_email: str, sender_auth_code: str, receiver_email: str):
        self.sender_email = sender_email
        self.sender_auth_code = sender_auth_code
        self.receiver_email = receiver_email

    def GuessSmtpConfig(self) -> tuple[str, int, bool]:
        domain = self.sender_email.rsplit("@", 1)[-1].lower()
        if domain in self.smtp_config_map:
            return self.smtp_config_map[domain]
        print(f"[警告] 未知邮箱后缀 @{domain}，默认尝试 smtp.{domain}:465")
        return f"smtp.{domain}", 465, True

    def Send(self, assignments: list[Assignment]) -> bool:
        if not assignments:
            print("没有需要通知的作业。")
            return True

        host, port, use_ssl = self.GuessSmtpConfig()
        lines = [f"共发现未提交作业 {len(assignments)} 项：\n"]
        for index, assignment in enumerate(assignments, start=1):
            lines.extend([
                f"{index}. [{assignment.platform_name}] {assignment.course_name}",
                f"   作业: {assignment.assignment_name}",
                f"   状态: {assignment.status}",
                f"   截止: {assignment.due_date_str}",
                f"   链接: {assignment.url}",
                "-" * 20,
            ])

        message = EmailMessage()
        message["Subject"] = f"[{assignments[0].platform_name}] 发现未交作业 {len(assignments)} 项"
        message["From"] = self.sender_email
        message["To"] = self.receiver_email
        message.set_content("\n".join(lines))

        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                server.starttls()
            server.login(self.sender_email, self.sender_auth_code)
            server.send_message(message)
            server.quit()
            print(f"邮件已成功发送至 {self.receiver_email}")
            return True
        except (OSError, smtplib.SMTPException) as exc:
            print(f"邮件发送失败: {exc}")
            return False


def main() -> int:
    try:
        config = ReminderConfig.Load()
    except ValueError as exc:
        print(f"配置错误: {exc}")
        return 2

    scraper = GradescopeScraper()
    if not scraper.Login(config.gradescope_email, config.gradescope_password):
        print("Gradescope 登录失败。")
        return 1

    assignments = scraper.FetchUnsubmittedAssignments()
    if not assignments:
        print("\n没有需要提醒的未交作业。")
        return 0

    print(f"\n--- 汇总结果：共 {len(assignments)} 项未交作业 ---")
    notifier = EmailNotifier(config.sender_email, config.sender_auth_code, config.receiver_email)
    # TODO: Add a Qmsg notifier after implementing its API request.
    return 0 if notifier.Send(assignments) else 1


if __name__ == "__main__":
    raise SystemExit(main())
