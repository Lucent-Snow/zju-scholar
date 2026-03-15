"""zju_console.py — 控制台编码兼容（Windows / Claude Code 等环境下避免 UnicodeEncodeError）"""

import sys


def ensure_utf8_io() -> None:
    """确保 stdout/stderr 使用 UTF-8 输出，避免打印中文时 UnicodeEncodeError。"""
    try:
        enc = (sys.stdout.encoding or "").lower()
        if enc in ("utf-8", "utf8"):
            return
    except Exception:
        pass
    try:
        import io

        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
    except Exception:
        pass
