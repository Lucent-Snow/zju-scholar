"""zju_academic.py — 教务数据查询脚本

用法:
  python zju_academic.py courses --year 2024 --semester 1   # 获取课表
  python zju_academic.py grades                              # 获取成绩和 GPA
  python zju_academic.py exams                               # 获取考试安排
  python zju_academic.py todos                               # 获取作业/DDL

需要先通过 zju_login.py 登录。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zju_api import ZdbkApi, CoursesApi, calculate_gpa
from zju_cache import CacheManager

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
SESSION_FILE = DATA_DIR / "session.json"


def load_session() -> dict:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _get_webvpn():
    """从 session 中恢复 WebVPN 状态。"""
    session = load_session()
    if session.get("webvpn_enabled") and session.get("webvpn_cookies"):
        from zju_webvpn import WebVpnSession
        vpn = WebVpnSession()
        vpn.cookies = session["webvpn_cookies"]
        vpn.logged_in = True
        return vpn
    return None


def get_zdbk_api() -> ZdbkApi:
    session = load_session()
    webvpn = _get_webvpn()
    if webvpn:
        # WebVPN 模式: 不需要 ZDBK cookies，WebVPN 代理内部管理
        return ZdbkApi({}, webvpn=webvpn)
    cookies = session.get("zdbk_cookies")
    if not cookies:
        print("错误: 未登录教务网。请先运行 python zju_login.py", file=sys.stderr)
        sys.exit(1)
    return ZdbkApi(cookies)


def get_courses_api() -> CoursesApi:
    session = load_session()
    webvpn = _get_webvpn()
    if webvpn:
        # WebVPN 模式: 不需要 session cookie，WebVPN 代理内部管理
        return CoursesApi("", webvpn=webvpn)
    session_cookie = session.get("courses_session")
    if not session_cookie:
        print("错误: 未登录学在浙大。请先运行 python zju_login.py", file=sys.stderr)
        sys.exit(1)
    return CoursesApi(session_cookie)


cache = CacheManager()


async def cmd_courses(year: str, semester: str):
    api = get_zdbk_api()

    cache_key = f"timetable_{year}_{semester}"
    cached = cache.get(cache_key, "timetable")
    if cached:
        print(json.dumps(cached, ensure_ascii=False, indent=2))
        return

    sessions = await api.get_timetable(year, semester)
    cache.set(cache_key, sessions, "timetable")
    print(json.dumps(sessions, ensure_ascii=False, indent=2))


async def cmd_grades():
    api = get_zdbk_api()

    cached = cache.get("grades_all", "grades")
    if cached:
        print(json.dumps(cached, ensure_ascii=False, indent=2))
        return

    grades = await api.get_grades()

    try:
        major_grades = await api.get_major_grades()
        major_ids = {g["id"] for g in major_grades}
        for g in grades:
            if g["id"] in major_ids:
                g["major"] = True
    except Exception:
        pass

    gpa = calculate_gpa(grades)
    result = {"grades": grades, "gpa": gpa}
    cache.set("grades_all", result, "grades")
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_exams():
    api = get_zdbk_api()

    cached = cache.get("exams_all", "exams")
    if cached:
        print(json.dumps(cached, ensure_ascii=False, indent=2))
        return

    exams = await api.get_exams()
    cache.set("exams_all", exams, "exams")
    print(json.dumps(exams, ensure_ascii=False, indent=2))


async def cmd_todos():
    api = get_courses_api()

    cached = cache.get("todos", "todos")
    if cached:
        print(json.dumps(cached, ensure_ascii=False, indent=2))
        return

    todos = await api.get_todos()
    cache.set("todos", todos, "todos")
    print(json.dumps(todos, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="浙大教务数据查询")
    sub = parser.add_subparsers(dest="command", required=True)

    p_courses = sub.add_parser("courses", help="获取课表")
    p_courses.add_argument("--year", required=True, help="学年起始年份，如 2024")
    p_courses.add_argument("--semester", required=True, help="1=秋冬, 2=春夏, 3=短学期")

    sub.add_parser("grades", help="获取成绩和 GPA")
    sub.add_parser("exams", help="获取考试安排")
    sub.add_parser("todos", help="获取作业/DDL")

    args = parser.parse_args()

    try:
        if args.command == "courses":
            asyncio.run(cmd_courses(args.year, args.semester))
        elif args.command == "grades":
            asyncio.run(cmd_grades())
        elif args.command == "exams":
            asyncio.run(cmd_exams())
        elif args.command == "todos":
            asyncio.run(cmd_todos())
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
