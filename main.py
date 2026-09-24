import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
import os
import smtplib
from email.message import EmailMessage
import time
from datetime import datetime, timedelta, timezone

# --- 常量定义 ---
# Gradescope 的主页和登录相关的 URL
BASE_URL = "https://www.gradescope.com"
LOGIN_URL = f"{BASE_URL}/login"

# --- 核心功能 ---


def safe_request(session: requests.Session, method: str, url: str, retries: int = 2, timeout: int = 10, backoff: int = 1, **kwargs):
    """
    A small wrapper around session.get/post that adds timeout and simple retries.

    Returns the Response on success, or None on persistent failure.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            if method.lower() == "get":
                resp = session.get(url, timeout=timeout, **kwargs)
            else:
                resp = session.post(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            print(f"Request error ({method.upper()}) {url!r} attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2

    if last_exc is not None:
        print(f"Failed to fetch {url!r} after {retries} attempts. Last error: {last_exc!r}")
    else:
        print(f"Failed to fetch {url!r} after {retries} attempts.")
    return None


def login_to_gradescope(session, email, password):
    """
    处理登录逻辑，返回一个保持登录状态的 session 对象。
    """
    # 1. GET 请求：访问登录页面
    print("正在访问登录页面...")
    get_response = safe_request(session, "get", LOGIN_URL)
    if get_response is None:
        print("访问登录页面失败: 多次尝试均未成功。")
        return None

    # 2. 解析 HTML，并以最健壮的方式找到 authenticity_token
    soup = BeautifulSoup(get_response.text, "html.parser")
    token_element = soup.find("meta", {"name": "csrf-token"})

    # 明确检查找到的元素是否是一个“标签”，这是消除类型错误的根本方法
    if not isinstance(token_element, Tag):
        print("无法在页面上找到 'csrf-token' meta 标签，登录失败。")
        return None

    authenticity_token = token_element.get("content")
    if not authenticity_token:
        print("找到了 'csrf-token' 标签，但其中没有 'content' 属性，登录失败。")
        return None
    
    print("成功获取 authenticity_token。")

    # 3. 构造 POST 请求的 payload
    payload = {
        "session[email]": email,
        "session[password]": password,
        "authenticity_token": authenticity_token,
        "commit": "Log In"
    }

    # 4. 发送 POST 请求，完成登录
    print("正在提交登录信息...")
    post_response = safe_request(session, "post", LOGIN_URL, data=payload)
    if post_response is None:
        print("提交登录信息失败: 多次尝试均未成功。")
        return None

    # 5. 验证登录是否成功
    # 根据我们的实验，登录成功后可能跳转到 /courses 或 /account
    successful_urls = [f"{BASE_URL}/courses", f"{BASE_URL}/account"]
    if post_response.url in successful_urls:
        print("登录成功！")
        return session
    else:
        print("登录失败，请检查账号或密码。")
        print(f"提示：登录后页面停留在 {post_response.url} (预期为 {successful_urls[0]} 或 {successful_urls[1]})")
        return None


def get_courses(session: requests.Session) -> list[dict[str, str]]:
    """
    Fetches all courses from the Gradescope dashboard.

    Args:
        session: The logged-in requests session.

    Returns:
        A list of dictionaries, where each dictionary represents a course
        and contains 'name' and 'url'.
    """
    courses_url = "https://www.gradescope.com/account"
    response = safe_request(session, "get", courses_url)
    if response is None:
        print("Error fetching courses page: 多次尝试均未成功。")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    courses = []
    # Find all course links on the page. Try multiple selectors for robustness.
    course_tags = soup.select(".courseList--coursesForTerm a.courseBox[href^='/courses/']")
    if not course_tags:
        course_tags = soup.select("a.courseBox")
    # DEBUG 输出已注释，如需调试请临时取消注释
    # print(f"DEBUG: Found {len(course_tags)} potential course anchors")
    for tag in course_tags:
        if isinstance(tag, Tag):
            course_name_tag = tag.find("div", class_="courseBox--name")
            course_term_tag = tag.find("div", class_="courseBox--shortTerm")
            
            name: str | None = None
            term: str | None = None
            if isinstance(course_name_tag, Tag):
                name = course_name_tag.get_text(strip=True)
            if isinstance(course_term_tag, Tag):
                term = course_term_tag.get_text(strip=True)

            if not name:
                # Fallback to anchor text if structured name not found
                name = tag.get_text(strip=True)

            href = tag.get("href")
            if href and isinstance(href, str):
                # If term not found inside the anchor, try to lookup from the surrounding section
                if not term:
                    parent_section = tag.find_parent("div", class_="courseList")
                    if isinstance(parent_section, Tag):
                        term_tag = parent_section.find("div", class_="courseList--term")
                        if isinstance(term_tag, Tag):
                            term = term_tag.get_text(strip=True)

                full_name = f"{name} - {term}" if term else name
                courses.append({"name": full_name, "url": f"https://www.gradescope.com{href}"})

    return courses


def get_assignments(session: requests.Session, course_url: str) -> list[dict[str, str]]:
    """
    获取课程作业，并过滤掉已过期超过 24 小时的未提交作业。
    """
    print(f"Fetching assignments from {course_url}...")
    response = safe_request(session, "get", course_url)
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    unsubmitted_assignments = []

    table_body = soup.select_one("table#assignments-student-table tbody")
    if not isinstance(table_body, Tag):
        print("  [DEBUG] 未找到作业表格主体")
        return []

    assignment_rows = list(table_body.find_all("tr", recursive=False))
    now = datetime.now(timezone.utc)

    for row in assignment_rows:
        if not isinstance(row, Tag):
            continue

        # 1. 提取名称
        name_th = row.find("th", scope="row")
        if not name_th: continue
        name = name_th.get_text(strip=True)

        # 2. 提取状态
        all_tds = row.find_all("td")
        if not all_tds: continue
        status_text = all_tds[0].get_text(strip=True)

        # 过滤掉非 "No Submission" 的作业
        if "No Submission" not in status_text:
            continue

        # 3. 提取链接
        link_a = name_th.find("a")
        href = link_a.get("href") if link_a else None
        link = BASE_URL + href if isinstance(href, str) else course_url

        # 4. 提取所有截止日期并取最晚的一个
        due_date_text = "N/A"
        is_too_late = False
        
        # 找出该行内所有截止日期标签
        time_tags = row.find_all("time", class_="submissionTimeChart--dueDate")
        
        parsed_dates = []
        for t in time_tags:
            dt_str = t.get("datetime")
            if isinstance(dt_str, str):
                try:
                    # 解析逻辑
                    iso_str = dt_str[:10] + "T" + dt_str[11:]
                    iso_str = iso_str.replace(" ", "")
                    if "+" in iso_str and ":" not in iso_str[-5:]:
                        iso_str = iso_str[:-2] + ":" + iso_str[-2:]
                    
                    parsed_dates.append({
                        "dt": datetime.fromisoformat(iso_str),
                        "text": t.get_text(strip=True)
                    })
                except Exception as e:
                    print(f"  [错误] 解析日期失败 '{dt_str}': {e}")

        if parsed_dates:
            # 找到最晚的一个日期（如果有 Late Due Date，通常它比 Due Date 晚）
            latest_info = max(parsed_dates, key=lambda x: x["dt"])
            max_due_dt = latest_info["dt"]
            due_date_text = latest_info["text"]

            # 如果存在多个日期，且最晚的是 Late Due Date，可以在显示上做个标记
            if len(parsed_dates) > 1:
                due_date_text += " (含 Late Deadline)"

            # 核心判断：以最晚的截止时间为准，增加 24h 宽限期
            if now > (max_due_dt + timedelta(hours=24)):
                print(f"  [过滤] 作业 '{name}' 所有提交机会（含迟交）均已过期超过 24h")
                is_too_late = True
            else:
                # 只要还有一个截止日期没过期（或在宽限期内），就保留
                pass 
        else:
            print(f"  [警告] 作业 '{name}' 未找到任何时间标签")

        if not is_too_late:
            unsubmitted_assignments.append({
                "name": name,
                "link": link,
                "status": status_text,
                "due_date": due_date_text
            })

    return unsubmitted_assignments

def send_notification(assignments: list[dict[str, str]]) -> None:
    host = os.getenv("SMTP_HOST")
    port_str = os.getenv("SMTP_PORT", "465")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    to_addr = os.getenv("SMTP_TO")
    from_addr = os.getenv("SMTP_FROM") or user
    debug = os.getenv("SMTP_DEBUG") == "1"

    try:
        port = int(port_str)
    except ValueError:
        print(f"Error: SMTP_PORT must be an integer, got {port_str!r}")
        return

    # 基础校验
    if not all([host, port, user, password, to_addr, from_addr]):
        print("Error: Missing SMTP environment variables (SMTP_HOST/PORT/USER/PASSWORD/TO).")
        return
    if not assignments:
        print("No assignments to notify; skipping email.")
        return

    # 为静态类型收窄：运行至此说明变量均非空
    assert isinstance(host, str)
    assert isinstance(user, str)
    assert isinstance(password, str)
    assert isinstance(to_addr, str)
    assert isinstance(from_addr, str)

    # 组装正文
    lines = [f"共发现未提交作业 {len(assignments)} 项："]
    for i, a in enumerate(assignments, start=1):
        course = a.get("course_name", "(未识别课程)")
        name = a.get("name", "(未识别作业)")
        status = a.get("status", "")
        due = a.get("due_date", "")
        link = a.get("link", "")
        lines.append(f"{i}. 课程: {course}")
        lines.append(f"   作业: {name}")
        if status:
            lines.append(f"   状态: {status}")
        if due:
            lines.append(f"   截止: {due}")
        if link:
            lines.append(f"   链接: {link}")
        lines.append("-" * 20)
    body = "\n".join(lines)

    subject = f"[Gradescope] 未提交作业 {len(assignments)} 项"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    # 建立连接并发送，区分 SSL(465) 与 STARTTLS(587)
    if port == 465:
        server = None
        try:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
            if debug:
                server.set_debuglevel(1)
                print(f"SMTP DEBUG: using SSL connect to {host}:{port}")
            server.ehlo()
            server.login(user, password)
            server.send_message(msg)
            print("Notification email sent.")
        except Exception as e:
            print("Error during SMTP SSL send:", repr(e))
        finally:
            if server:
                try:
                    server.close()
                except Exception:
                    pass
    else:
        server = None
        try:
            server = smtplib.SMTP(host, port, timeout=15)
            if debug:
                server.set_debuglevel(1)
                print(f"SMTP DEBUG: using STARTTLS connect to {host}:{port}")
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
            server.send_message(msg)
            print("Notification email sent.")
        except Exception as e:
            print("Error during SMTP STARTTLS send:", repr(e))
        finally:
            if server:
                try:
                    server.close()
                except Exception:
                    pass
def send_qmsg_notification(assignments: list[dict[str, str]]) -> None:
    """
    通过 Qmsg 酱发送 QQ 通知。
    """
    qmsg_key = os.getenv("QMSG_KEY")
    # 如果你想发送给特定 QQ（在后台绑定的多个 QQ 之一），可以设置这个环境变量
    target_qq = os.getenv("QMSG_QQ") 

    if not qmsg_key:
        print("Error: QMSG_KEY environment variable is not set. Skipping QQ notification.")
        return

    if not assignments:
        return

    # 构造简短的 QQ 消息内容
    msg_lines = [f"【Gradescope提醒】发现 {len(assignments)} 项未交作业："]
    for i, a in enumerate(assignments, start=1):    
        name = a.get("name", "未知作业")
        due = a.get("due_date", "无截止日期")
        msg_lines.append(f"{i}. {name}")
        msg_lines.append(f"   截止: {due}")
    
    msg_content = "\n".join(msg_lines)

    # Qmsg API URL
    url = f"https://qmsg.zendee.cn/send/{qmsg_key}"
    
    data = {
        "msg": msg_content
    }
    if target_qq:
        data["qq"] = target_qq

    try:
        # 使用 requests 发送 POST 请求
        response = requests.post(url, data=data, timeout=10)
        result = response.json()
        if result.get("code") == 0:
            print("QQ notification sent successfully via Qmsg.")
        else:
            print(f"Failed to send QQ notification: {result.get('txt')}")
    except Exception as e:
        print(f"Error occurred while sending Qmsg: {e}")

# --- 主程序入口 ---

if __name__ == "__main__":
    session = requests.Session()
    # 设置常见浏览器请求头，避免因默认 UA 被服务器屏蔽或返回简化页面
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Referer": "https://www.gradescope.com/login"
    })

    # Load email and password from environment variables
    email = os.getenv("GRADESCOPE_EMAIL")
    password = os.getenv("GRADESCOPE_PASSWORD")

    if not email or not password:
        print("Error: GRADESCOPE_EMAIL and GRADESCOPE_PASSWORD environment variables must be set.")
    else:
        logged_in_session = login_to_gradescope(session, email, password)

        if logged_in_session:
            print("Login successful.")
            courses = get_courses(logged_in_session)
            if not courses:
                print("No courses found.")
            else:
                print(f"Found {len(courses)} courses.")
                all_unsubmitted_assignments = []
                for course in courses:
                    print(f"\nChecking course: {course['name']}")
                    unsubmitted_assignments = get_assignments(logged_in_session, course['url'])
                    if unsubmitted_assignments:
                        for assignment in unsubmitted_assignments:
                            assignment['course_name'] = course['name'] # Add course name to assignment info
                        all_unsubmitted_assignments.extend(unsubmitted_assignments)

                # 测试注入逻辑已注释（不再在生产环境自动注入假作业）。
                # 如需再次启用，可临时取消下面的注释块。
                # if not all_unsubmitted_assignments and os.getenv("SMTP_FORCE_TEST") == "1":
                #     print("INFO: SMTP_FORCE_TEST=1 detected — injecting test assignment for email test.")
                #     all_unsubmitted_assignments = [
                #         {
                #             "course_name": "测试课程",
                #             "name": "测试作业",
                #             "status": "No Submission",
                #             "due_date": "N/A",
                #             "link": "https://www.gradescope.com"
                #         }
                #     ]

                if not all_unsubmitted_assignments:
                    print("\nNo unsubmitted assignments found in any course. Great job!")
                else:
                    print("\n--- Summary of Unsubmitted Assignments ---")
                    for assignment in all_unsubmitted_assignments:
                        print(f"  Course: {assignment['course_name']}")
                        print(f"  Assignment: {assignment['name']}")
                        print(f"  Status: {assignment['status']}")
                        print(f"  Due Date: {assignment['due_date']}")
                        print("-" * 20)

                    # 打印全部条目后只发送一次邮件通知（避免重复发送）
                    send_notification(all_unsubmitted_assignments)
                    send_qmsg_notification(all_unsubmitted_assignments)
        else:
            print("Login failed.")