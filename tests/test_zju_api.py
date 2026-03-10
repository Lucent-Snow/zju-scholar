import asyncio
import sys
import unittest
from unittest.mock import AsyncMock
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zju_api import CoursesApi


class CoursesApiTests(unittest.TestCase):
    def test_normalize_course(self):
        raw = {
            "id": 123,
            "name": "Test Course",
            "course_code": "ABC123",
            "department": {"id": 1, "name": "Dept"},
            "instructors": [{"id": 9, "name": "Teacher A"}],
            "course_attributes": {"teaching_class_name": "Class 1"},
            "start_date": "2026-03-01",
            "url": "https://courses.zju.edu.cn/course/123/content",
            "cover": "",
            "status": "in_progress",
        }
        normalized = CoursesApi._normalize_course(raw)
        self.assertEqual(normalized["id"], 123)
        self.assertEqual(normalized["department"], "Dept")
        self.assertEqual(normalized["instructors"], ["Teacher A"])
        self.assertEqual(normalized["teaching_class_name"], "Class 1")

    def test_extract_filename(self):
        req = httpx.Request("GET", "https://courses.zju.edu.cn/api/uploads/1/blob")
        resp = httpx.Response(
            200,
            request=req,
            headers={"Content-Disposition": "attachment; filename*=utf-8''hello%20world.pdf"},
        )
        filename = CoursesApi._extract_filename(resp, "fallback.bin")
        self.assertEqual(filename, "hello world.pdf")

    def test_course_matches_statuses(self):
        self.assertTrue(CoursesApi._course_matches_statuses({"status": "in_progress"}, ["ongoing"]))
        self.assertFalse(CoursesApi._course_matches_statuses({"status": "in_progress"}, ["finished"]))
        self.assertTrue(CoursesApi._course_matches_statuses({"status": "finished"}, ["finished"]))

    def test_normalize_courseware_activity(self):
        raw = {
            "id": 99,
            "title": "课件",
            "type": "material",
            "module_id": 7,
            "course_id": 123,
            "uploads": [
                {
                    "id": 1,
                    "name": "slides.pdf",
                    "type": "document",
                    "size": 42,
                    "status": "ready",
                    "allow_download": True,
                }
            ],
        }
        items = CoursesApi._normalize_courseware_activity(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["activity_id"], 99)
        self.assertEqual(items[0]["upload_id"], 1)
        self.assertEqual(items[0]["name"], "slides.pdf")

    def test_get_coursewares_reads_uploads_from_activities(self):
        api = CoursesApi("session-token")
        api._request_json = AsyncMock(
            return_value={
                "total": 2,
                "pages": 1,
                "activities": [
                    {
                        "id": 10,
                        "title": "第一讲",
                        "type": "material",
                        "uploads": [{"id": 1, "name": "a.pdf"}],
                    },
                    {
                        "id": 11,
                        "title": "第二讲",
                        "type": "material",
                        "uploads": [{"id": 2, "name": "b.pdf"}],
                    },
                ],
            }
        )

        result = asyncio.run(api.get_coursewares(123))

        self.assertEqual(result["total"], 2)
        self.assertEqual([item["upload_id"] for item in result["coursewares"]], [1, 2])

    def test_get_my_courses_finished_aggregates_semesters(self):
        api = CoursesApi("session-token")

        async def fake_request_json(method, path, **kwargs):
            if method == "GET" and path == "/api/my-semesters":
                return {
                    "semesters": [
                        {"id": 79, "is_active": True},
                        {"id": 76, "is_active": False},
                    ]
                }
            if method == "POST" and path == "/api/my-courses":
                semester_id = kwargs["json_body"]["conditions"].get("semester_id")
                if semester_id == 79:
                    return {
                        "courses": [
                            {
                                "id": 94379,
                                "name": "游泳（初级）",
                                "course_code": "CURRENT",
                                "semester_id": 79,
                                "status": "in_progress",
                            }
                        ]
                    }
                if semester_id == 76:
                    return {
                        "courses": [
                            {
                                "id": 89632,
                                "name": "认知神经科学专题",
                                "course_code": "FINISHED",
                                "semester_id": 76,
                                "status": "ended",
                            }
                        ]
                    }
            raise AssertionError(f"unexpected request: {method} {path} {kwargs}")

        api._request_json = AsyncMock(side_effect=fake_request_json)

        result = asyncio.run(api.get_my_courses(statuses=["finished"], page=1, page_size=10))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["courses"][0]["id"], 89632)
        self.assertEqual(result["courses"][0]["status"], "ended")


if __name__ == "__main__":
    unittest.main()
