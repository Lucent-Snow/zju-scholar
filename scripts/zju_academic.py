"""zju_academic.py — 教务数据查询脚本

用法:
  python zju_academic.py courses                             # 获取当前学期课表（自动推算）
  python zju_academic.py courses --year 2024 --semester 1    # 获取指定学期课表
  python zju_academic.py grades                              # 获取所有成绩和 GPA
  python zju_academic.py grades --current                    # 仅当前学期成绩
  python zju_academic.py exams                               # 获取当前学期考试安排（默认）
  python zju_academic.py exams --all                         # 获取所有考试安排
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
from zju_session import get_courses_api, get_zdbk_api, current_semester, semester_label


cache = CacheManager()


async def cmd_courses(year: str | None, semester: str | None):
    if not year or not semester:
        year, semester = current_semester()
    api = get_zdbk_api()

    cache_key = f"timetable_{year}_{semester}"
    cached = cache.get(cache_key, "timetable")
    if cached:
        emit_success(
            platform="academic",
            feature="timetable",
            data=cached,
            meta={"year": year, "semester": semester, "label": semester_label(year, semester)},
            source="cache",
        )
        return

    sessions = await api.get_timetable(year, semester)
    cache.set(cache_key, sessions, "timetable")
    emit_success(
        platform="academic",
        feature="timetable",
        data=sessions,
        meta={"year": year, "semester": semester, "label": semester_label(year, semester)},
    )


async def cmd_grades(year: str | None = None, semester: str | None = None):
    api = get_zdbk_api()

    cache_key = "grades_all"
    cached = cache.get(cache_key, "grades")
    if cached:
        grades_data = cached
    else:
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
        grades_data = {"grades": grades, "gpa": gpa}
        cache.set(cache_key, grades_data, "grades")

    # 按学期过滤
    if year and semester:
        y = int(year)
        year_prefix = f"({year}-{y+1}-{semester})"
        filtered = [g for g in grades_data["grades"] if g["id"].startswith(year_prefix)]
        filtered_gpa = calculate_gpa(filtered)
        label = semester_label(year, semester)
        emit_success(
            platform="academic",
            feature="grades",
            data={"grades": filtered, "gpa": filtered_gpa, "all_gpa": grades_data["gpa"]},
            meta={"year": year, "semester": semester, "label": label, "filtered": True},
        )
    else:
        emit_success(
            platform="academic",
            feature="grades",
            data=grades_data,
            source="cache" if cached else "live",
        )


async def cmd_exams(show_all: bool = False, year: str | None = None, semester: str | None = None):
    api = get_zdbk_api()

    cached = cache.get("exams_all", "exams")
    if cached:
        all_exams = cached
    else:
        all_exams = await api.get_exams()
        cache.set("exams_all", all_exams, "exams")

    if show_all:
        emit_success(
            platform="academic",
            feature="exams",
            data=all_exams,
            meta={"filtered": False, "total": len(all_exams)},
            source="cache" if cached else "live",
        )
        return

    # 默认过滤到当前学期
    if not year or not semester:
        year, semester = current_semester()
    y = int(year)
    year_prefix = f"({year}-{y+1}-{semester})"
    filtered = [e for e in all_exams if e["id"].startswith(year_prefix)]
    label = semester_label(year, semester)

    emit_success(
        platform="academic",
        feature="exams",
        data=filtered,
        meta={"year": year, "semester": semester, "label": label, "filtered": True, "total": len(filtered)},
        source="cache" if cached else "live",
    )


async def cmd_todos():
    """作业/DDL 查询已移至 zju_courses.py todos，此处保留兼容入口。"""
    from zju_courses import cmd_todos as _courses_todos
    await _courses_todos()


def main():
    parser = argparse.ArgumentParser(description="浙大教务数据查询")
    sub = parser.add_subparsers(dest="command", required=True)

    p_courses = sub.add_parser("courses", help="获取课表（默认当前学期）")
    p_courses.add_argument("--year", default=None, help="学年起始年份，如 2025（不传则自动推算）")
    p_courses.add_argument("--semester", default=None, help="1=秋冬, 2=春夏, 3=短学期（不传则自动推算）")

    p_grades = sub.add_parser("grades", help="获取成绩和 GPA")
    p_grades.add_argument("--current", action="store_true", help="仅显示当前学期成绩")
    p_grades.add_argument("--year", default=None, help="按学年过滤")
    p_grades.add_argument("--semester", default=None, help="按学期过滤")

    p_exams = sub.add_parser("exams", help="获取考试安排（默认当前学期）")
    p_exams.add_argument("--all", action="store_true", dest="show_all", help="显示所有学期考试")
    p_exams.add_argument("--year", default=None, help="按学年过滤")
    p_exams.add_argument("--semester", default=None, help="按学期过滤")

    sub.add_parser("todos", help="获取作业/DDL（等价于 zju_courses.py todos）")

    args = parser.parse_args()

    try:
        if args.command == "courses":
            asyncio.run(cmd_courses(args.year, args.semester))
        elif args.command == "grades":
            grade_year = args.year
            grade_semester = args.semester
            if args.current and not grade_year:
                grade_year, grade_semester = current_semester()
            asyncio.run(cmd_grades(grade_year, grade_semester))
        elif args.command == "exams":
            asyncio.run(cmd_exams(show_all=args.show_all, year=args.year, semester=args.semester))
        elif args.command == "todos":
            asyncio.run(cmd_todos())
    except RuntimeError as e:
        emit_error(message=str(e) or e.__class__.__name__, platform="academic", feature=args.command)
    except Exception as e:
        emit_error(message=str(e) or e.__class__.__name__, platform="academic", feature=args.command)


if __name__ == "__main__":
    main()
