import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zju_cc98 import CC98Api, _token_expired, build_parser


class CC98Tests(unittest.TestCase):
    def test_token_expired(self):
        self.assertTrue(_token_expired(0))
        self.assertFalse(_token_expired(int(time.time()) + 3600))

    def test_build_search_path_global(self):
        path = CC98Api._build_search_path("常微分", from_offset=0, size=5)
        self.assertEqual(path, "/topic/search?keyword=%E5%B8%B8%E5%BE%AE%E5%88%86&from=0&size=5")

    def test_build_search_path_board(self):
        path = CC98Api._build_search_path("常微分", from_offset=10, size=20, board_id=68)
        self.assertEqual(path, "/topic/search/board/68?keyword=%E5%B8%B8%E5%BE%AE%E5%88%86&from=10&size=20")

    def test_normalize_topic_summary(self):
        raw = {
            "id": 1,
            "boardId": 68,
            "boardName": "学习天地",
            "title": "常微分方程求助",
            "time": "2026-03-26T12:00:00+08:00",
            "userId": 2,
            "userName": "Alice",
            "replyCount": 3,
            "hitCount": 99,
            "lastPostUser": "Bob",
            "lastPostTime": "2026-03-26T13:00:00+08:00",
            "lastPostContent": "内容",
            "state": 0,
        }
        normalized = CC98Api._normalize_topic_summary(raw)
        self.assertEqual(normalized["board_name"], "学习天地")
        self.assertEqual(normalized["reply_count"], 3)
        self.assertEqual(normalized["last_post_user"], "Bob")

    def test_normalize_post(self):
        raw = {
            "id": 10,
            "parentId": 0,
            "boardId": 68,
            "userId": 2,
            "userName": "Alice",
            "time": "2026-03-26T12:00:00+08:00",
            "content": "hello",
            "likeCount": 5,
            "dislikeCount": 0,
        }
        normalized = CC98Api._normalize_post(raw)
        self.assertEqual(normalized["content"], "hello")
        self.assertEqual(normalized["like_count"], 5)

    def test_parser_accepts_webvpn_after_subcommand(self):
        args = build_parser().parse_args(["hot", "--webvpn"])
        self.assertEqual(args.command, "hot")
        self.assertTrue(args.webvpn)

    def test_parser_accepts_webvpn_before_subcommand(self):
        args = build_parser().parse_args(["--webvpn", "search", "--keyword", "常微分"])
        self.assertEqual(args.command, "search")
        self.assertTrue(args.webvpn)
        self.assertEqual(args.keyword, "常微分")


if __name__ == "__main__":
    unittest.main()
