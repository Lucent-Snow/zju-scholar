"""统一会话加载与 API 构造。"""

from __future__ import annotations

import json
from pathlib import Path

from zju_api import CoursesApi, ZdbkApi
from zju_zhiyun import ZhiyunApi

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
SESSION_FILE = DATA_DIR / "session.json"
CREDENTIALS_FILE = DATA_DIR / "credentials.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_session() -> dict:
    return _read_json(SESSION_FILE)


def load_credentials() -> dict:
    return _read_json(CREDENTIALS_FILE)


def restore_webvpn(session: dict | None = None):
    session = session or load_session()
    if session.get("webvpn_enabled") and session.get("webvpn_cookies"):
        from zju_webvpn import WebVpnSession

        vpn = WebVpnSession()
        vpn.cookies = session["webvpn_cookies"]
        vpn.logged_in = True
        return vpn
    return None


def get_zdbk_api(session: dict | None = None) -> ZdbkApi:
    session = session or load_session()
    webvpn = restore_webvpn(session)
    if webvpn:
        return ZdbkApi({}, webvpn=webvpn)

    cookies = session.get("zdbk_cookies")
    if not cookies:
        raise RuntimeError("未登录教务网。请先运行 python scripts/zju_login.py")
    return ZdbkApi(cookies)


def get_courses_api(session: dict | None = None) -> CoursesApi:
    session = session or load_session()
    webvpn = restore_webvpn(session)
    if webvpn:
        return CoursesApi("", webvpn=webvpn)

    session_cookie = session.get("courses_session")
    if not session_cookie:
        raise RuntimeError("未登录学在浙大。请先运行 python scripts/zju_login.py")
    return CoursesApi(session_cookie)


def get_zhiyun_api(session: dict | None = None, credentials: dict | None = None) -> ZhiyunApi:
    session = session or load_session()
    credentials = credentials or load_credentials()
    webvpn = restore_webvpn(session)

    jwt = session.get("zhiyun_jwt") or credentials.get("zhiyun_token")
    student_id = session.get("username") or credentials.get("username", "")
    user_id = str(session.get("user_id", ""))

    if not jwt:
        raise RuntimeError(
            "未设置智云 JWT。请先运行 python scripts/zju_login.py 或通过 --zhiyun-token 设置。"
        )

    return ZhiyunApi(jwt=jwt, student_id=student_id, user_id=user_id, webvpn=webvpn)
