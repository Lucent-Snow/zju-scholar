"""统一 JSON 输出工具。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_utf8_stream(stream) -> None:
    encoding = (getattr(stream, "encoding", "") or "").lower()
    if encoding == "utf-8":
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    except (OSError, ValueError):
        return


def make_success_response(
    *,
    platform: str,
    feature: str,
    data,
    meta: dict | None = None,
    source: str = "live",
) -> dict:
    return {
        "ok": True,
        "platform": platform,
        "feature": feature,
        "source": source,
        "generated_at": _utc_now_iso(),
        "meta": meta or {},
        "data": data,
    }


def make_error_response(
    *,
    message: str,
    platform: str = "",
    feature: str = "",
    details=None,
) -> dict:
    message = message.strip() if isinstance(message, str) else str(message)
    if not message:
        message = "UnknownError"
    payload = {
        "ok": False,
        "platform": platform,
        "feature": feature,
        "generated_at": _utc_now_iso(),
        "error": {
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def emit_success(
    *,
    platform: str,
    feature: str,
    data,
    meta: dict | None = None,
    source: str = "live",
) -> None:
    _ensure_utf8_stream(sys.stdout)
    print(
        json.dumps(
            make_success_response(
                platform=platform,
                feature=feature,
                data=data,
                meta=meta,
                source=source,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def emit_error(
    *,
    message: str,
    platform: str = "",
    feature: str = "",
    details=None,
    exit_code: int = 1,
) -> None:
    _ensure_utf8_stream(sys.stderr)
    print(
        json.dumps(
            make_error_response(
                message=message,
                platform=platform,
                feature=feature,
                details=details,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        file=sys.stderr,
    )
    raise SystemExit(exit_code)
