"""zju_courses.py — 学在浙大数据查询脚本。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zju_cache import CacheManager
from zju_output import emit_error, emit_success
from zju_session import get_courses_api

cache = CacheManager()


def _list_cache_key(prefix: str, *parts) -> str:
    clean_parts = [str(part) for part in parts if part not in (None, "", [], ())]
    return "_".join([prefix, *clean_parts]) if clean_parts else prefix


async def cmd_course_list(keyword: str, page: int, page_size: int, statuses: list[str]):
    api = get_courses_api()
    cache_key = _list_cache_key("courses_list_v4", keyword or "__all__", page, page_size, ",".join(statuses))
    cached = cache.get(cache_key, "courses_list")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="course_list",
            data=cached,
            meta={"keyword": keyword, "page": page, "page_size": page_size, "statuses": statuses},
            source="cache",
        )
        return

    result = await api.get_my_courses(keyword=keyword, page=page, page_size=page_size, statuses=statuses)
    cache.set(cache_key, result, "courses_list")
    emit_success(
        platform="courses",
        feature="course_list",
        data=result,
        meta={"keyword": keyword, "page": page, "page_size": page_size, "statuses": statuses},
    )


async def cmd_course_detail(course_id: str):
    api = get_courses_api()
    cache_key = f"course_detail_{course_id}"
    cached = cache.get(cache_key, "course_detail")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="course_detail",
            data=cached,
            meta={"course_id": course_id},
            source="cache",
        )
        return

    result = await api.get_course_detail(course_id)
    cache.set(cache_key, result, "course_detail")
    emit_success(
        platform="courses",
        feature="course_detail",
        data=result,
        meta={"course_id": course_id},
    )


async def cmd_modules(course_id: str):
    api = get_courses_api()
    cache_key = f"course_modules_{course_id}"
    cached = cache.get(cache_key, "course_modules")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="course_modules",
            data=cached,
            meta={"course_id": course_id},
            source="cache",
        )
        return

    result = await api.get_course_modules(course_id)
    cache.set(cache_key, result, "course_modules")
    emit_success(
        platform="courses",
        feature="course_modules",
        data=result,
        meta={"course_id": course_id},
    )


async def cmd_activities(course_id: str, sub_course_id: int):
    api = get_courses_api()
    cache_key = f"course_activities_{course_id}_{sub_course_id}"
    cached = cache.get(cache_key, "course_activities")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="course_activities",
            data=cached,
            meta={"course_id": course_id, "sub_course_id": sub_course_id},
            source="cache",
        )
        return

    result = await api.get_course_activities(course_id, sub_course_id=sub_course_id)
    cache.set(cache_key, result, "course_activities")
    emit_success(
        platform="courses",
        feature="course_activities",
        data=result,
        meta={"course_id": course_id, "sub_course_id": sub_course_id},
    )


async def cmd_activity(activity_id: str):
    api = get_courses_api()
    cache_key = f"activity_detail_{activity_id}"
    cached = cache.get(cache_key, "activity_detail")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="activity_detail",
            data=cached,
            meta={"activity_id": activity_id},
            source="cache",
        )
        return

    result = await api.get_activity_detail(activity_id)
    cache.set(cache_key, result, "activity_detail")
    emit_success(
        platform="courses",
        feature="activity_detail",
        data=result,
        meta={"activity_id": activity_id},
    )


async def cmd_classrooms(course_id: str):
    api = get_courses_api()
    cache_key = f"course_classrooms_{course_id}"
    cached = cache.get(cache_key, "course_classrooms")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="course_classrooms",
            data=cached,
            meta={"course_id": course_id},
            source="cache",
        )
        return

    result = await api.get_course_classrooms(course_id)
    cache.set(cache_key, result, "course_classrooms")
    emit_success(
        platform="courses",
        feature="course_classrooms",
        data=result,
        meta={"course_id": course_id},
    )


async def cmd_classroom(classroom_id: str):
    api = get_courses_api()
    cache_key = f"classroom_detail_{classroom_id}"
    cached = cache.get(cache_key, "classroom_detail")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="classroom_detail",
            data=cached,
            meta={"classroom_id": classroom_id},
            source="cache",
        )
        return

    result = await api.get_classroom_subject(classroom_id)
    cache.set(cache_key, result, "classroom_detail")
    emit_success(
        platform="courses",
        feature="classroom_detail",
        data=result,
        meta={"classroom_id": classroom_id},
    )


async def cmd_coursewares(course_id: str, page: int, page_size: int, category: str):
    api = get_courses_api()
    cache_key = _list_cache_key("coursewares_v2", course_id, page, page_size, category or "__all__")
    cached = cache.get(cache_key, "coursewares")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="coursewares",
            data=cached,
            meta={"course_id": course_id, "page": page, "page_size": page_size, "category": category},
            source="cache",
        )
        return

    result = await api.get_coursewares(course_id, page=page, page_size=page_size, category=category or None)
    cache.set(cache_key, result, "coursewares")
    emit_success(
        platform="courses",
        feature="coursewares",
        data=result,
        meta={"course_id": course_id, "page": page, "page_size": page_size, "category": category},
    )


async def cmd_todos():
    api = get_courses_api()
    cached = cache.get("todos", "todos")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="todo_list",
            data=cached,
            source="cache",
        )
        return

    result = await api.get_todos()
    cache.set("todos", result, "todos")
    emit_success(
        platform="courses",
        feature="todo_list",
        data=result,
    )


async def cmd_resources(keyword: str, file_type: str, page: int, page_size: int):
    api = get_courses_api()
    cache_key = _list_cache_key("resources_list", keyword or "__all__", file_type, page, page_size)
    cached = cache.get(cache_key, "resources_list")
    if cached is not None:
        emit_success(
            platform="courses",
            feature="resource_list",
            data=cached,
            meta={"keyword": keyword, "file_type": file_type, "page": page, "page_size": page_size},
            source="cache",
        )
        return

    result = await api.get_user_resources(keyword=keyword, file_type=file_type, page=page, page_size=page_size)
    cache.set(cache_key, result, "resources_list")
    emit_success(
        platform="courses",
        feature="resource_list",
        data=result,
        meta={"keyword": keyword, "file_type": file_type, "page": page, "page_size": page_size},
    )


async def cmd_resource_download(resource_id: str, output_dir: str):
    api = get_courses_api()
    result = await api.download_resource(resource_id, Path(output_dir))
    emit_success(
        platform="courses",
        feature="resource_download",
        data=result,
        meta={"resource_id": resource_id, "output_dir": str(Path(output_dir).resolve())},
    )


async def cmd_resource_upload(file_path: str):
    api = get_courses_api()
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        emit_error(message=f"文件不存在: {path}", platform="courses", feature="resource_upload")
    result = await api.upload_resource(path)
    emit_success(
        platform="courses",
        feature="resource_upload",
        data=result,
        meta={"file_path": str(path)},
    )


def main():
    from zju_console import ensure_utf8_io
    ensure_utf8_io()
    parser = argparse.ArgumentParser(description="学在浙大数据查询")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("course-list", help="列出课程")
    p_list.add_argument("--keyword", default="", help="课程关键词")
    p_list.add_argument("--page", type=int, default=1, help="页码")
    p_list.add_argument("--page-size", type=int, default=20, help="每页数量")
    p_list.add_argument(
        "--status",
        action="append",
        dest="statuses",
        choices=["ongoing", "notStarted", "finished"],
        help="课程状态，可重复传入；默认 ongoing + notStarted",
    )

    p_detail = sub.add_parser("course-detail", help="课程详情")
    p_detail.add_argument("--course-id", required=True, help="课程 ID")

    p_modules = sub.add_parser("modules", help="课程模块")
    p_modules.add_argument("--course-id", required=True, help="课程 ID")

    p_activities = sub.add_parser("activities", help="课程活动列表")
    p_activities.add_argument("--course-id", required=True, help="课程 ID")
    p_activities.add_argument("--sub-course-id", type=int, default=0, help="子课程 ID")

    p_activity = sub.add_parser("activity", help="活动详情")
    p_activity.add_argument("--activity-id", required=True, help="活动 ID")

    p_classrooms = sub.add_parser("classrooms", help="课堂互动列表")
    p_classrooms.add_argument("--course-id", required=True, help="课程 ID")

    p_classroom = sub.add_parser("classroom", help="课堂互动详情/题目")
    p_classroom.add_argument("--classroom-id", required=True, help="课堂互动 ID")

    p_coursewares = sub.add_parser("coursewares", help="课程资料列表")
    p_coursewares.add_argument("--course-id", required=True, help="课程 ID")
    p_coursewares.add_argument("--page", type=int, default=1, help="页码")
    p_coursewares.add_argument("--page-size", type=int, default=20, help="每页数量")
    p_coursewares.add_argument("--category", default="", help="资料分类")

    sub.add_parser("todos", help="待办任务列表")

    p_resources = sub.add_parser("resources", help="云盘资源列表")
    p_resources.add_argument("--keyword", default="", help="资源关键词")
    p_resources.add_argument(
        "--type",
        dest="file_type",
        default="all",
        choices=["all", "file", "video", "document", "image", "audio", "scorm", "swf", "link"],
        help="资源类型",
    )
    p_resources.add_argument("--page", type=int, default=1, help="页码")
    p_resources.add_argument("--page-size", type=int, default=20, help="每页数量")

    p_download = sub.add_parser("resource-download", help="下载云盘资源")
    p_download.add_argument("--resource-id", required=True, help="资源 ID")
    p_download.add_argument("--output-dir", default=".", help="输出目录")

    p_upload = sub.add_parser("resource-upload", help="上传文件到云盘")
    p_upload.add_argument("--file", required=True, help="待上传文件路径")

    args = parser.parse_args()

    statuses = getattr(args, "statuses", None) or ["ongoing", "notStarted"]

    try:
        if args.command == "course-list":
            asyncio.run(cmd_course_list(args.keyword, args.page, args.page_size, statuses))
        elif args.command == "course-detail":
            asyncio.run(cmd_course_detail(args.course_id))
        elif args.command == "modules":
            asyncio.run(cmd_modules(args.course_id))
        elif args.command == "activities":
            asyncio.run(cmd_activities(args.course_id, args.sub_course_id))
        elif args.command == "activity":
            asyncio.run(cmd_activity(args.activity_id))
        elif args.command == "classrooms":
            asyncio.run(cmd_classrooms(args.course_id))
        elif args.command == "classroom":
            asyncio.run(cmd_classroom(args.classroom_id))
        elif args.command == "coursewares":
            asyncio.run(cmd_coursewares(args.course_id, args.page, args.page_size, args.category))
        elif args.command == "todos":
            asyncio.run(cmd_todos())
        elif args.command == "resources":
            asyncio.run(cmd_resources(args.keyword, args.file_type, args.page, args.page_size))
        elif args.command == "resource-download":
            asyncio.run(cmd_resource_download(args.resource_id, args.output_dir))
        elif args.command == "resource-upload":
            asyncio.run(cmd_resource_upload(args.file))
    except RuntimeError as e:
        emit_error(message=str(e) or e.__class__.__name__, platform="courses", feature=args.command)
    except Exception as e:
        emit_error(message=str(e) or e.__class__.__name__, platform="courses", feature=args.command)


if __name__ == "__main__":
    main()
