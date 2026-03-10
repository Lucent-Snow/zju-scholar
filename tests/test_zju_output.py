import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zju_output import make_error_response, make_success_response


class ZjuOutputTests(unittest.TestCase):
    def test_make_success_response(self):
        payload = make_success_response(
            platform="courses",
            feature="course_list",
            data=[{"id": 1}],
            meta={"page": 1},
            source="cache",
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["platform"], "courses")
        self.assertEqual(payload["feature"], "course_list")
        self.assertEqual(payload["source"], "cache")
        self.assertEqual(payload["data"][0]["id"], 1)
        self.assertEqual(payload["meta"]["page"], 1)

    def test_make_error_response_falls_back_when_message_empty(self):
        payload = make_error_response(message="  ")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["message"], "UnknownError")


if __name__ == "__main__":
    unittest.main()
