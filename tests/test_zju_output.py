import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zju_output import _ensure_utf8_stream


class DummyStream:
    def __init__(self, encoding: str):
        self.encoding = encoding
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)
        self.encoding = kwargs.get("encoding", self.encoding)


class OutputTests(unittest.TestCase):
    def test_ensure_utf8_stream_reconfigures_non_utf8_stream(self):
        stream = DummyStream("gbk")
        _ensure_utf8_stream(stream)
        self.assertEqual(stream.encoding, "utf-8")
        self.assertEqual(stream.calls, [{"encoding": "utf-8", "errors": "backslashreplace"}])

    def test_ensure_utf8_stream_skips_utf8_stream(self):
        stream = DummyStream("utf-8")
        _ensure_utf8_stream(stream)
        self.assertEqual(stream.calls, [])


if __name__ == "__main__":
    unittest.main()
