"""zju_api.py — 教务网 ZDBK + 学在浙大 Courses API

翻译自 Celechron Dart 代码:
- lib/http/zjuServices/zdbk.dart    — 课表/成绩/考试 API
- lib/http/zjuServices/courses.dart  — Todos API
- lib/model/grade.dart               — 成绩转换映射
- lib/model/session.dart             — 课程 session 解析
- lib/model/exam.dart + exams_dto.dart — 考试解析
- lib/utils/gpa_helper.dart          — GPA 计算
"""

import re
import json
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

    def __init__(self, cookies: dict, timeout: float = 8.0):
        self.cookies = cookies
        self.timeout = timeout

    async def _post(self, url: str, data: str = "") -> str:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self.timeout,
            verify=True,
        ) as client:
            resp = await client.post(
                url,
                content=data,
                cookies=self.cookies,
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
        sessions = []
        for item in raw_list:
            if item.get("kcb"):
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

    def __init__(self, session_cookie: str, timeout: float = 8.0):
        self.session_cookie = session_cookie
        self.timeout = timeout

    async def get_todos(self) -> list[dict]:
        """获取作业/DDL 列表。"""
        async with httpx.AsyncClient(
            timeout=self.timeout,
            verify=True,
        ) as client:
            resp = await client.get(
                f"{COURSES_BASE}/api/todos",
                cookies={"session": self.session_cookie},
            )
            data = resp.json()

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
