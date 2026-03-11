"""统一会话加载与 API 构造。"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from zju_api import CoursesApi, ZdbkApi
from zju_zhiyun import ZhiyunApi

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
SESSION_FILE = DATA_DIR / "session.json"
CREDENTIALS_FILE = DATA_DIR / "credentials.json"
PROFILE_FILE = DATA_DIR / "profile.json"


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


def load_profile() -> dict:
    """加载用户学业档案。返回 {grade, year, semester, label, campus, ...}。"""
    return _read_json(PROFILE_FILE)


def save_profile(profile: dict):
    """保存用户学业档案。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def current_semester() -> tuple[str, str]:
    """获取当前学期。优先读 profile.json，否则按日期推算。

    返回 (year, semester)。
    """
    profile = load_profile()
    if profile.get("year") and profile.get("semester"):
        return profile["year"], profile["semester"]

    # fallback: 按日期推算
    now = datetime.now(timezone(timedelta(hours=8)))
    month = now.month
    year = now.year

    if month >= 9:
        return str(year), "1"
    elif month <= 1:
        return str(year - 1), "1"
    elif 2 <= month <= 6:
        return str(year - 1), "2"
    else:
        return str(year - 1), "3"


def semester_label(year: str | None = None, semester: str | None = None) -> str:
    """生成可读的学期标签，如 '2025-2026 春夏（大二下）'。"""
    if not year or not semester:
        year, semester = current_semester()
    y = int(year)
    sem_names = {"1": "秋冬", "2": "春夏", "3": "短学期"}
    label = f"{y}-{y+1} {sem_names.get(semester, semester)}"

    profile = load_profile()
    if profile.get("year") == year and profile.get("semester") == semester and profile.get("grade"):
        label += f"（{profile['grade']}）"
    return label


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
