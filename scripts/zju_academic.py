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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zju_api import ZdbkApi, CoursesApi, calculate_gpa
from zju_cache import CacheManager
from zju_output import emit_error, emit_success
from zju_session import get_courses_api, get_zdbk_api


cache = CacheManager()


async def cmd_courses(year: str, semester: str):
    api = get_zdbk_api()

    cache_key = f"timetable_{year}_{semester}"
    cached = cache.get(cache_key, "timetable")
    if cached:
        emit_success(
            platform="academic",
            feature="timetable",
            data=cached,
            meta={"year": year, "semester": semester},
            source="cache",
        )
        return

    sessions = await api.get_timetable(year, semester)
    cache.set(cache_key, sessions, "timetable")
    emit_success(
        platform="academic",
        feature="timetable",
        data=sessions,
        meta={"year": year, "semester": semester},
    )


async def cmd_grades():
    api = get_zdbk_api()

    cached = cache.get("grades_all", "grades")
    if cached:
        emit_success(
            platform="academic",
            feature="grades",
            data=cached,
            source="cache",
        )
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
    emit_success(
        platform="academic",
        feature="grades",
        data=result,
    )


async def cmd_exams():
    api = get_zdbk_api()

    cached = cache.get("exams_all", "exams")
    if cached:
        emit_success(
            platform="academic",
            feature="exams",
            data=cached,
            source="cache",
        )
        return

    exams = await api.get_exams()
    cache.set("exams_all", exams, "exams")
    emit_success(
        platform="academic",
        feature="exams",
        data=exams,
    )


async def cmd_todos():
    api = get_courses_api()

    cached = cache.get("todos", "todos")
    if cached:
        emit_success(
            platform="academic",
            feature="todo_list",
            data=cached,
            source="cache",
        )
        return

    todos = await api.get_todos()
    cache.set("todos", todos, "todos")
    emit_success(
        platform="academic",
        feature="todo_list",
        data=todos,
    )


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
    except RuntimeError as e:
        emit_error(message=str(e) or e.__class__.__name__, platform="academic", feature=args.command)
    except Exception as e:
        emit_error(message=str(e) or e.__class__.__name__, platform="academic", feature=args.command)


if __name__ == "__main__":
    main()
