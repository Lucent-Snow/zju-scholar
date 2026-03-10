"""zju_api.py — 教务网 ZDBK + 学在浙大 Courses API

翻译自 Celechron Dart 代码:
- lib/http/zjuServices/zdbk.dart    — 课表/成绩/考试 API
- lib/http/zjuServices/courses.dart  — Todos API
- lib/model/grade.dart               — 成绩转换映射
- lib/model/session.dart             — 课程 session 解析
- lib/model/exam.dart + exams_dto.dart — 考试解析
- lib/utils/gpa_helper.dart          — GPA 计算
"""

import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote

import httpx

ZDBK_BASE = "https://zdbk.zju.edu.cn/jwglxt"
COURSES_BASE = "https://courses.zju.edu.cn"

# --- Grade conversion maps (from grade.dart) ---

TO_FOUR_POINT = {
    5.0: 4.3,
    4.8: 4.2,
    4.5: 4.1,
    4.2: 4.0,
}

TO_HUNDRED_POINT = {
    "A+": 95, "A": 90, "A-": 87,
    "B+": 83, "B": 80, "B-": 77,
    "C+": 73, "C": 70, "C-": 67,
    "D": 60, "F": 0,
    "优秀": 90, "良好": 80, "中等": 70,
    "及格": 60, "不及格": 0,
    "合格": 75, "不合格": 0,
    "弃修": 0, "缺考": 0, "缓考": 0,
    "待录": 0, "无效": 0,
}

SEMESTER_MAP = {
    "秋冬": "1",   # 第一学期
    "春夏": "2",   # 第二学期
    "秋": "1",
    "冬": "1",
    "春": "2",
    "夏": "2",
    "短": "3",     # 短学期
}

COURSE_STATUS_QUERY_MAP = {
    "ongoing": "in_progress",
    "notStarted": "not_started",
    "finished": "finished",
}

COURSE_STATUS_ALIASES = {
    "ongoing": {"ongoing", "in_progress"},
    "notStarted": {"notStarted", "not_started"},
    "finished": {"finished", "ended", "completed", "closed"},
}

COURSE_LIST_FIELDS = (
    "id,name,course_code,academic_year_id,semester_id,course_attributes(teaching_class_name),"
    "department(id,name),instructors(id,name),start_date,url,cover,status"
)


# --- Parsing functions ---

def parse_grade(raw: dict) -> dict:
    """Parse a grade item from ZDBK API response (grade.dart Grade constructor)."""
    course_id = raw.get("xkkh", "")
    name = raw.get("kcmc", "").replace("(", "（").replace(")", "）")
    credit = float(raw.get("xf", "0"))
    original = raw.get("cj", "")
    five_point = float(raw.get("jd", "0"))

    # Hundred point conversion
    hundred_point = TO_HUNDRED_POINT.get(original)
    if hundred_point is None:
        digit_match = re.search(r"\d+", original)
        hundred_point = int(digit_match.group(0)) if digit_match else 0

    # Four point conversion
    four_point = TO_FOUR_POINT.get(five_point, five_point) if five_point > 4.0 else five_point
    four_point_legacy = 4.0 if five_point > 4.0 else five_point

    # Inclusion flags
    credit_included = original not in ("弃修", "待录", "缓考", "无效")
    gpa_included = credit_included and original not in ("合格", "不合格") and "xtwkc" not in course_id

    # Earned credit
    earned_credit = credit if (credit_included and (five_point != 0 or "xtwkc" in course_id)) else 0.0

    return {
        "id": course_id,
        "name": name,
        "credit": credit,
        "original": original,
        "five_point": five_point,
        "four_point": four_point,
        "four_point_legacy": four_point_legacy,
        "hundred_point": hundred_point,
        "gpa_included": gpa_included,
        "credit_included": credit_included,
        "earned_credit": earned_credit,
    }


def parse_session(raw: dict) -> dict | None:
    """Parse a timetable session from ZDBK API response (session.dart Session.fromZdbk)."""
    if "kcb" not in raw:
        return None

    confirmed = raw.get("sfqd", "0") == "1"
    day_of_week = int(raw.get("xqj", "1"))

    dsz = raw.get("dsz", "2")
    odd_week = dsz != "1"   # not 双周only
    even_week = dsz != "0"  # not 单周only

    # Parse name, teacher, location from kcb field
    kcb = raw.get("kcb", "")
    match = re.match(r"(.*?)<br>(.*?)<br>(.*?)<br>(.*?)zwf", kcb)
    if not match:
        return None

    name = match.group(1).replace("(", "（").replace(")", "）")
    teacher = match.group(3)
    location = match.group(4) if match.group(4) else None

    # Semester half
    first_half = False
    second_half = False
    if "xxq" in raw:
        semester = raw["xxq"]
        first_half = "秋" in semester or "春" in semester
        second_half = "冬" in semester or "夏" in semester

    # Time slots
    time_slots = []
    if "djj" in raw and "skcd" in raw:
        initial = int(raw["djj"])
        duration = int(raw["skcd"])
        time_slots = list(range(initial, initial + duration))

    return {
        "name": name,
        "teacher": teacher,
        "location": location,
        "confirmed": confirmed,
        "day_of_week": day_of_week,
        "odd_week": odd_week,
        "even_week": even_week,
        "first_half": first_half,
        "second_half": second_half,
        "time_slots": time_slots,
    }


def parse_exam_time(datetime_str: str) -> dict:
    """Parse exam datetime string (time_helper.dart parseExamDateTime).

    Input format: "2021年01月22日(08:00-10:00)" or "第N天(HH:MM-HH:MM)"
    """
    if "年" in datetime_str:
        date = f"{datetime_str[0:4]}-{datetime_str[5:7]}-{datetime_str[8:10]}"
        time_begin = datetime_str[12:17]
        time_end = datetime_str[18:23]
    else:
        m = re.search(r"第(\d+)天\((.+)-(.+)\)", datetime_str)
        if m:
            day = m.group(1).zfill(2)
            date = f"1970-01-{day}"
            time_begin = m.group(2)
            time_end = m.group(3)
        else:
            date = "1970-01-14"
            time_begin = "00:00"
            time_end = "00:00"

    return {
        "date": date,
        "start_time": time_begin,
        "end_time": time_end,
        "start": f"{date}T{time_begin}",
        "end": f"{date}T{time_end}",
    }


def parse_exam(raw: dict) -> dict:
    """Parse an exam item from ZDBK API response (exam.dart + exams_dto.dart)."""
    course_id = raw.get("xkkh", "")
    name = raw.get("kcmc", "").replace("(", "（").replace(")", "）")
    credit = float(raw.get("xf", "0"))

    exams = []

    # Midterm exam (期中)
    if "qzkssj" in raw and raw["qzkssj"]:
        time_info = parse_exam_time(raw["qzkssj"])
        exams.append({
            "type": "midterm",
            "time": time_info,
            "location": raw.get("qzjsmc", ""),
            "seat": raw.get("qzzwxh", ""),
        })

    # Final exam (期末)
    if "kssj" in raw and raw["kssj"]:
        time_info = parse_exam_time(raw["kssj"])
        exams.append({
            "type": "final",
            "time": time_info,
            "location": raw.get("jsmc", ""),
            "seat": raw.get("zwxh", ""),
        })

    return {
        "id": course_id,
        "name": name,
        "credit": credit,
        "exams": exams,
    }


def calculate_gpa(grades: list[dict]) -> dict:
    """Calculate GPA from parsed grades (gpa_helper.dart calculateGpa).

    Returns dict with five_point, four_point, four_point_legacy, hundred_point GPAs,
    plus total_credits and earned_credits.
    """
    earned_credits = sum(g["earned_credit"] for g in grades)

    gpa_grades = [g for g in grades if g["gpa_included"]]
    gpa_credit_total = sum(g["credit"] for g in gpa_grades)

    if gpa_credit_total == 0:
        return {
            "five_point_gpa": 0.0,
            "four_point_gpa": 0.0,
            "four_point_legacy_gpa": 0.0,
            "hundred_point_gpa": 0.0,
            "gpa_credits": 0.0,
            "earned_credits": earned_credits,
            "total_courses": len(grades),
        }

    five_sum = sum(g["five_point"] * g["credit"] for g in gpa_grades)
    four_sum = sum(g["four_point"] * g["credit"] for g in gpa_grades)
    four_legacy_sum = sum(g["four_point_legacy"] * g["credit"] for g in gpa_grades)
    hundred_sum = sum(g["hundred_point"] * g["credit"] for g in gpa_grades)

    return {
        "five_point_gpa": round(five_sum / gpa_credit_total, 4),
        "four_point_gpa": round(four_sum / gpa_credit_total, 4),
        "four_point_legacy_gpa": round(four_legacy_sum / gpa_credit_total, 4),
        "hundred_point_gpa": round(hundred_sum / gpa_credit_total, 4),
        "gpa_credits": gpa_credit_total,
        "earned_credits": earned_credits,
        "total_courses": len(grades),
    }


# --- API classes ---

class ZdbkApi:
    """教务网 ZDBK API client."""

    def __init__(self, cookies: dict, timeout: float = 15.0, webvpn=None):
        self.cookies = cookies
        self.timeout = timeout
        self._webvpn = webvpn

    def _url(self, url: str) -> str:
        if self._webvpn and self._webvpn.logged_in:
            from zju_webvpn import convert_url
            return convert_url(url)
        return url

    def _make_client(self, **kwargs) -> httpx.AsyncClient:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", True)
        if self._webvpn and self._webvpn.logged_in:
            kwargs.setdefault("follow_redirects", True)
            return self._webvpn.make_client(**kwargs)
        kwargs.setdefault("follow_redirects", False)
        return httpx.AsyncClient(**kwargs)

    async def _post(self, url: str, data: str = "") -> str:
        async with self._make_client() as client:
            resp = await client.post(
                self._url(url),
                content=data,
                cookies=self.cookies if not (self._webvpn and self._webvpn.logged_in) else {},
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            )
            return resp.text

    async def get_timetable(self, year: str, semester: str) -> list[dict]:
        """获取课表。year: e.g. "2024", semester: "1"(秋冬) / "2"(春夏) / "3"(短)"""
        # Semester code mapping: ZDBK uses specific codes
        sem_code_map = {"1": "3", "2": "12", "3": "16"}
        sem_code = sem_code_map.get(semester, semester)

        body = f"xnm={year}&xqm={sem_code}"
        html = await self._post(f"{ZDBK_BASE}/kbcx/xskbcx_cxXsKb.html", body)

        match = re.search(r'(?<="kbList":)\[(.*?)\](?=,"xh")', html)
        if not match:
            raise RuntimeError("无法解析课表数据")

        raw_list = json.loads(match.group(0))

        # 按学年过滤：xkkh 格式为 "(2025-2026-1)-XXX"，提取学年起始年份
        year_int = int(year)
        year_prefix = f"({year}-{year_int + 1}-"

        sessions = []
        for item in raw_list:
            if not item.get("kcb"):
                continue
            # 过滤非当前学年的课程
            xkkh = item.get("xkkh", "")
            if xkkh and not xkkh.startswith(year_prefix):
                continue
            parsed = parse_session(item)
            if parsed:
                sessions.append(parsed)

        return sessions

    async def get_grades(self) -> list[dict]:
        """获取所有成绩。"""
        html = await self._post(
            f"{ZDBK_BASE}/cxdy/xscjcx_cxXscjIndex.html?doType=query&queryModel.showCount=5000"
        )

        match = re.search(r'(?<="items":)\[(.*?)\](?=,"limit")', html)
        if not match:
            raise RuntimeError("无法解析成绩数据")

        raw_list = json.loads(match.group(0))
        return [parse_grade(item) for item in raw_list if item.get("xkkh")]

    async def get_major_grades(self) -> list[dict]:
        """获取主修成绩。"""
        html = await self._post(
            f"{ZDBK_BASE}/zycjtj/xszgkc_cxXsZgkcIndex.html?doType=query&queryModel.showCount=5000"
        )

        match = re.search(r'(?<="items":)\[(.*?)\](?=,"limit")', html)
        if not match:
            raise RuntimeError("无法解析主修成绩数据")

        raw_list = json.loads(match.group(0))
        grades = [parse_grade(item) for item in raw_list if item.get("xkkh")]
        for g in grades:
            g["major"] = True
        return grades

    async def get_exams(self) -> list[dict]:
        """获取考试安排。"""
        html = await self._post(
            f"{ZDBK_BASE}/xskscx/kscx_cxXsgrksIndex.html?doType=query&queryModel.showCount=5000"
        )

        match = re.search(r'(?<="items":)\[(.*?)\](?=,"limit")', html)
        if not match:
            raise RuntimeError("无法解析考试数据")

        raw_list = json.loads(match.group(0))
        return [parse_exam(item) for item in raw_list if item.get("xkkh")]


class CoursesApi:
    """学在浙大 Courses API client."""

    def __init__(self, session_cookie: str, timeout: float = 15.0, webvpn=None):
        self.session_cookie = session_cookie
        self.timeout = timeout
        self._webvpn = webvpn

    def _url(self, url: str) -> str:
        if self._webvpn and self._webvpn.logged_in:
            from zju_webvpn import convert_url
            return convert_url(url)
        return url

    def _make_client(self, **kwargs) -> httpx.AsyncClient:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", True)
        if self._webvpn and self._webvpn.logged_in:
            kwargs.setdefault("follow_redirects", True)
            return self._webvpn.make_client(**kwargs)
        return httpx.AsyncClient(**kwargs)

    def _request_cookies(self) -> dict:
        if self._webvpn and self._webvpn.logged_in:
            return {}
        return {"session": self.session_cookie}

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        request_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
        }
        if headers:
            request_headers.update(headers)

        async with self._make_client() as client:
            resp = await client.request(
                method,
                self._url(f"{COURSES_BASE}{path}"),
                params=params,
                json=json_body,
                headers=request_headers,
                cookies=self._request_cookies(),
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _normalize_course(raw: dict) -> dict:
        department = raw.get("department") or {}
        instructors = raw.get("instructors") or []
        attributes = raw.get("course_attributes") or {}

        return {
            "id": raw.get("id"),
            "name": raw.get("name", ""),
            "course_code": raw.get("course_code", ""),
            "department": department.get("name", "") if isinstance(department, dict) else "",
            "department_id": department.get("id") if isinstance(department, dict) else None,
            "instructors": [
                item.get("name", "")
                for item in instructors
                if isinstance(item, dict) and item.get("name")
            ],
            "teaching_class_name": attributes.get("teaching_class_name", "") if isinstance(attributes, dict) else "",
            "start_date": raw.get("start_date", ""),
            "url": raw.get("url", ""),
            "cover": raw.get("cover", ""),
            "status": raw.get("status", ""),
        }

    @staticmethod
    def _normalize_course_status(value: str) -> str:
        raw = str(value or "").strip()
        for normalized, aliases in COURSE_STATUS_ALIASES.items():
            if raw in aliases:
                return normalized
        return raw

    @classmethod
    def _course_matches_statuses(cls, course: dict, statuses: list[str] | None) -> bool:
        if not statuses:
            return True
        normalized_status = cls._normalize_course_status(course.get("status", ""))
        requested = {status for status in statuses if status}
        return normalized_status in requested

    @staticmethod
    def _paginate_courses(courses: list[dict], page: int, page_size: int) -> dict:
        total = len(courses)
        if page_size <= 0:
            page_size = total or 1
        start = max(page - 1, 0) * page_size
        end = start + page_size
        return {
            "total": total,
            "pages": (total + page_size - 1) // page_size if total else 0,
            "page": page,
            "page_size": page_size,
            "courses": courses[start:end],
        }

    async def _list_my_courses(self, *, page: int, page_size: int, conditions: dict) -> dict:
        payload = {
            "page": page,
            "page_size": page_size,
            "fields": COURSE_LIST_FIELDS,
            "conditions": conditions,
        }
        return await self._request_json("POST", "/api/my-courses", json_body=payload)

    async def get_my_semesters(self) -> list[dict]:
        data = await self._request_json("GET", "/api/my-semesters")
        return data.get("semesters", [])

    async def _get_courses_by_semesters(
        self,
        *,
        keyword: str,
        semester_ids: list[int],
        statuses: list[str] | None,
    ) -> list[dict]:
        courses = []
        seen_ids = set()
        for semester_id in semester_ids:
            data = await self._list_my_courses(
                page=1,
                page_size=100,
                conditions={
                    "keyword": keyword,
                    "semester_id": semester_id,
                },
            )
            for item in data.get("courses", []):
                course = self._normalize_course(item)
                course_id = course.get("id")
                if course_id in seen_ids:
                    continue
                if not self._course_matches_statuses(course, statuses):
                    continue
                seen_ids.add(course_id)
                courses.append(course)
        return courses

    @classmethod
    def _normalize_courseware_activity(cls, raw: dict) -> list[dict]:
        uploads = raw.get("uploads") or []
        items = []
        for upload in uploads:
            if not isinstance(upload, dict):
                continue
            items.append(
                {
                    "activity_id": raw.get("id"),
                    "activity_title": raw.get("title", ""),
                    "activity_type": raw.get("type", ""),
                    "module_id": raw.get("module_id"),
                    "course_id": raw.get("course_id"),
                    "upload_id": upload.get("id"),
                    "name": upload.get("name", ""),
                    "type": upload.get("type", ""),
                    "size": upload.get("size", 0),
                    "status": upload.get("status", ""),
                    "allow_download": upload.get("allow_download", False),
                    "created_at": upload.get("created_at", ""),
                    "updated_at": upload.get("updated_at", ""),
                    "key": upload.get("key", ""),
                    "raw": upload,
                }
            )
        return items

    @staticmethod
    def _normalize_resource(raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "name": raw.get("name", ""),
            "size": raw.get("size", 0),
            "updated_at": raw.get("updated_at", ""),
            "created_at": raw.get("created_at", ""),
            "file_type": raw.get("file_type", ""),
            "resource_type": raw.get("resource_type", ""),
            "ready": raw.get("ready", True),
            "parent_id": raw.get("parent_id", 0),
        }

    @staticmethod
    def _extract_filename(resp: httpx.Response, fallback: str) -> str:
        content_disposition = resp.headers.get("Content-Disposition", "")
        if "filename*=" in content_disposition:
            match = re.search(r"filename\*\s*=\s*utf-?8''([^;]+)", content_disposition, flags=re.I)
            if match:
                return unquote(match.group(1).strip('"'))
        if "filename=" in content_disposition:
            match = re.search(r'filename="?([^"]+)"?', content_disposition, flags=re.I)
            if match:
                return match.group(1)
        return fallback

    async def get_my_courses(
        self,
        *,
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
        statuses: list[str] | None = None,
    ) -> dict:
        statuses = statuses or ["ongoing", "notStarted"]
        if "finished" in statuses:
            semesters = await self.get_my_semesters()
            semester_ids = [item.get("id") for item in semesters if item.get("id") is not None]
            courses = await self._get_courses_by_semesters(
                keyword=keyword,
                semester_ids=semester_ids,
                statuses=statuses,
            )
            return self._paginate_courses(courses, page, page_size)

        query_statuses = [COURSE_STATUS_QUERY_MAP.get(status, status) for status in statuses]
        data = await self._list_my_courses(
            page=page,
            page_size=page_size,
            conditions={
                "keyword": keyword,
                "status": query_statuses,
            },
        )
        courses = [self._normalize_course(item) for item in data.get("courses", [])]
        courses = [course for course in courses if self._course_matches_statuses(course, statuses)]
        return {
            "total": data.get("total", len(courses)),
            "pages": data.get("pages", 0),
            "page": page,
            "page_size": page_size,
            "courses": courses,
        }

    async def get_course_detail(self, course_id: int | str) -> dict:
        data = await self._request_json(
            "GET",
            f"/api/courses/{course_id}",
            params={
                "fields": (
                    "id,name,course_code,course_type,credit,start_date,end_date,url,cover,"
                    "department(id,name),instructors(id,name),course_attributes(teaching_class_name,data)"
                )
            },
        )
        return data.get("course", data)

    async def get_course_modules(self, course_id: int | str) -> list[dict]:
        data = await self._request_json("GET", f"/api/courses/{course_id}/modules")
        return data.get("modules", [])

    async def get_course_activities(self, course_id: int | str, *, sub_course_id: int = 0) -> list[dict]:
        data = await self._request_json(
            "GET",
            f"/api/courses/{course_id}/activities",
            params={"sub_course_id": sub_course_id},
        )
        return data.get("activities", [])

    async def get_course_classrooms(self, course_id: int | str) -> list[dict]:
        data = await self._request_json("GET", f"/api/courses/{course_id}/classroom-list")
        return data.get("classrooms", [])

    async def get_activity_detail(self, activity_id: int | str) -> dict:
        return await self._request_json(
            "GET",
            f"/api/activities/{activity_id}",
            params={"sub_course_id": 0},
        )

    async def get_classroom_subject(self, classroom_id: int | str) -> dict:
        return await self._request_json("GET", f"/api/classroom/{classroom_id}/subject")

    async def get_coursewares(
        self,
        course_id: int | str,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
    ) -> dict:
        params = {
            "page": page,
            "page_size": page_size,
            "conditions": json.dumps(
                {
                    "category": category,
                    "itemsSortBy": {
                        "predicate": "chapter",
                        "reverse": False,
                    },
                    "ignore_activity_types": ["lesson"],
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        }
        data = await self._request_json("GET", f"/api/course/{course_id}/coursewares", params=params)
        activities = data.get("activities", [])
        coursewares = []
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            coursewares.extend(self._normalize_courseware_activity(activity))
        return {
            "page": page,
            "page_size": page_size,
            "total": data.get("total", 0),
            "pages": data.get("pages", 1),
            "coursewares": coursewares,
        }

    async def get_todos(self) -> list[dict]:
        """获取作业/DDL 列表。"""
        data = await self._request_json("GET", "/api/todos")

        todo_list = data.get("todo_list", [])
        return [
            {
                "id": str(item.get("id", "")),
                "title": item.get("title", ""),
                "course_name": item.get("course_name", ""),
                "course_code": item.get("course_code", ""),
                "type": item.get("type", ""),
                "end_time": item.get("end_time", ""),
                "is_locked": item.get("is_locked", False),
            }
            for item in todo_list
        ]

    async def get_user_resources(
        self,
        *,
        keyword: str = "",
        file_type: str = "all",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        params = {
            "page": page,
            "page_size": page_size,
            "conditions": json.dumps(
                {
                    "keyword": keyword,
                    "includeSlides": True,
                    "limitTypes": [],
                    "fileType": file_type,
                    "parentId": 0,
                    "folderToken": "",
                    "resourceType": None,
                    "filters": [],
                    "linkTypes": [],
                    "only_ready": False,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        }
        data = await self._request_json("GET", "/api/user/resources", params=params)
        uploads = [self._normalize_resource(item) for item in data.get("uploads", [])]
        return {
            "total": data.get("total", len(uploads)),
            "pages": data.get("pages", 1),
            "page": page,
            "page_size": page_size,
            "uploads": uploads,
        }

    async def download_resource(self, resource_id: int | str, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)

        async with self._make_client(follow_redirects=True) as client:
            async with client.stream(
                "GET",
                self._url(f"{COURSES_BASE}/api/uploads/{resource_id}/blob"),
                cookies=self._request_cookies(),
            ) as resp:
                resp.raise_for_status()
                fallback_name = f"resource_{resource_id}"
                filename = self._extract_filename(resp, fallback_name)
                file_path = output_dir / filename

                with open(file_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            f.write(chunk)

        return {
            "resource_id": str(resource_id),
            "filename": filename,
            "saved_to": str(file_path.resolve()),
            "size": file_path.stat().st_size,
        }

    async def upload_resource(self, file_path: Path) -> dict:
        payload = {
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "parent_type": None,
            "parent_id": 0,
            "is_scorm": False,
            "is_wmpkg": False,
            "source": "",
            "is_marked_attachment": False,
            "embed_material_type": "",
        }
        headers = {
            "Origin": "https://courses.zju.edu.cn",
            "Referer": "https://courses.zju.edu.cn/user/resources/files",
        }
        data = await self._request_json(
            "POST",
            "/api/uploads",
            json_body=payload,
            headers=headers,
        )

        upload_url = data.get("upload_url")
        if not upload_url:
            raise RuntimeError("资源上传失败：未获取到 upload_url")

        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

        async with self._make_client(follow_redirects=True) as client:
            with open(file_path, "rb") as f:
                resp = await client.put(
                    upload_url,
                    files={"file": (file_path.name, f.read(), mime)},
                )
            resp.raise_for_status()

        return {
            "id": data.get("id"),
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "uploaded": True,
        }
