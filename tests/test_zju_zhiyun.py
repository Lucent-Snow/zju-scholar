import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zju_zhiyun import ZhiyunApi


class ZhiyunApiTests(unittest.TestCase):
    def test_normalize_transcript_segments(self):
        transcript = {
            "list": [
                {"start_time": 1000, "end_time": 5000, "text": "嗯 你好"},
                {"start_time": 6000, "end_time": 9000, "text": "世界"},
            ]
        }
        segments = ZhiyunApi._normalize_transcript_segments(transcript)
        self.assertEqual(segments[0]["start_sec"], 1)
        self.assertEqual(segments[1]["text"], "世界")

    def test_format_subtitle_text_filters_fillers(self):
        transcript = {
            "list": [
                {"start_time": 1000, "end_time": 5000, "text": "嗯"},
                {"start_time": 6000, "end_time": 9000, "text": "你好"},
            ]
        }
        text = ZhiyunApi.format_subtitle_text(transcript, filter_fillers=True)
        self.assertEqual(text, "你好")


if __name__ == "__main__":
    unittest.main()
