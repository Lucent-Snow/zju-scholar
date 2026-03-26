"""zju_cc98.py — CC98 forum API + CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.parse
from pathlib import Path

import httpx

from zju_output import emit_error, emit_success
from zju_session import DATA_DIR, restore_webvpn

CC98_API_BASE = "https://api.cc98.org"
CC98_AUTH_URL = "https://openid.cc98.org/connect/token"
CC98_CLIENT_ID = "9a1fd200-8687-44b1-4c20-08d50a96e5cd"
CC98_CLIENT_SECRET = "8b53f727-08e2-4509-8857-e34bf92b27f2"
CC98_SCOPE = "cc98-api openid offline_access"

CC98_CREDENTIALS_FILE = DATA_DIR / "cc98_credentials.json"
CC98_SESSION_FILE = DATA_DIR / "cc98_session.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_cc98_credentials() -> dict:
    return _read_json(CC98_CREDENTIALS_FILE)


def save_cc98_credentials(username: str, password: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CC98_CREDENTIALS_FILE.write_text(
        json.dumps({"username": username, "password": password}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_cc98_session() -> dict:
    return _read_json(CC98_SESSION_FILE)


def save_cc98_session(session: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CC98_SESSION_FILE.write_text(
        json.dumps(session, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _token_expired(expires_at: int, *, skew_seconds: int = 60) -> bool:
    if not expires_at:
        return True
    return time.time() >= max(expires_at - skew_seconds, 0)


class CC98Api:
    """CC98 API client."""

    def __init__(
        self,
        *,
        access_token: str = "",
        refresh_token: str = "",
        expires_at: int = 0,
        timeout: float = 15.0,
        webvpn=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.timeout = timeout
        self._webvpn = webvpn

    def _url(self, url: str) -> str:
        if self._webvpn and self._webvpn.logged_in:
            from zju_webvpn import convert_url

            return convert_url(url)
        return url

    def _make_client(self, **kwargs) -> httpx.AsyncClient:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", True)
        kwargs.setdefault("follow_redirects", True)
        if self._webvpn and self._webvpn.logged_in:
            return self._webvpn.make_client(**kwargs)
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def _expires_at_from_response(payload: dict) -> int:
        expires_in = int(payload.get("expires_in", 0) or 0)
        return int(time.time()) + expires_in

    def _auth_header(self) -> dict:
        if not self.access_token:
            return {}
        token = self.access_token
        if not token.startswith("Bearer "):
            token = f"Bearer {token}"
        return {"Authorization": token}

    async def _token_request(self, form: dict) -> dict:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.cc98.org",
            "Referer": "https://www.cc98.org/",
        }
        async with self._make_client() as client:
            resp = await client.post(
                self._url(CC98_AUTH_URL),
                data=form,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        self.access_token = data.get("access_token", "")
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.expires_at = self._expires_at_from_response(data)
        return data

    async def login(self, username: str, password: str) -> dict:
        return await self._token_request(
            {
                "client_id": CC98_CLIENT_ID,
                "client_secret": CC98_CLIENT_SECRET,
                "grant_type": "password",
                "username": username,
                "password": password,
                "scope": CC98_SCOPE,
            }
        )

    async def refresh(self) -> dict:
        if not self.refresh_token:
            raise RuntimeError("CC98 refresh_token 不存在，请重新登录。")
        return await self._token_request(
            {
                "client_id": CC98_CLIENT_ID,
                "client_secret": CC98_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "scope": CC98_SCOPE,
            }
        )

    async def ensure_login(self, credentials: dict):
        if self.access_token and not _token_expired(self.expires_at):
            return
        if self.refresh_token:
            try:
                await self.refresh()
                return
            except Exception:
                pass
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        if not username or not password:
            raise RuntimeError("未保存 CC98 凭证，请先运行 python scripts/zju_cc98.py login")
        await self.login(username, password)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        auth_required: bool = False,
        credentials: dict | None = None,
    ):
        if auth_required:
            await self.ensure_login(credentials or {})

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.cc98.org",
            "Referer": "https://www.cc98.org/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }
        headers.update(self._auth_header())

        async with self._make_client() as client:
            resp = await client.request(method, self._url(f"{CC98_API_BASE}{path}"), headers=headers)
            if resp.status_code == 401:
                raise RuntimeError("CC98 接口鉴权失败，可能需要重新登录。")
            if resp.status_code == 403:
                text = resp.text.strip()
                if text == "last_search_in_1_seconds":
                    raise RuntimeError("CC98 搜索过于频繁，请至少等待 1 秒后重试。")
                raise RuntimeError(f"CC98 请求被拒绝: {text or resp.status_code}")
            resp.raise_for_status()
            return json.loads(resp.content.decode("utf-8"))

    @staticmethod
    def _build_search_path(keyword: str, *, from_offset: int, size: int, board_id: int = 0) -> str:
        encoded = urllib.parse.quote(keyword)
        if board_id > 0:
            return f"/topic/search/board/{board_id}?keyword={encoded}&from={from_offset}&size={size}"
        return f"/topic/search?keyword={encoded}&from={from_offset}&size={size}"

    @staticmethod
    def _normalize_topic_summary(raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "board_id": raw.get("boardId"),
            "board_name": raw.get("boardName", ""),
            "title": raw.get("title", ""),
            "time": raw.get("time", ""),
            "user_id": raw.get("userId"),
            "user_name": raw.get("userName", ""),
            "is_anonymous": raw.get("isAnonymous", False),
            "reply_count": raw.get("replyCount", 0),
            "hit_count": raw.get("hitCount", 0),
            "last_post_user": raw.get("lastPostUser", ""),
            "last_post_time": raw.get("lastPostTime", ""),
            "last_post_content": raw.get("lastPostContent", ""),
            "state": raw.get("state", 0),
        }

    @staticmethod
    def _normalize_topic_detail(raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "board_id": raw.get("boardId"),
            "title": raw.get("title", ""),
            "time": raw.get("time", ""),
            "user_id": raw.get("userId"),
            "user_name": raw.get("userName", ""),
            "is_anonymous": raw.get("isAnonymous", False),
            "reply_count": raw.get("replyCount", 0),
            "hit_count": raw.get("hitCount", 0),
            "last_post_user": raw.get("lastPostUser", ""),
            "last_post_time": raw.get("lastPostTime", ""),
            "best_state": raw.get("bestState", 0),
            "top_state": raw.get("topState", 0),
            "allowed_viewer_state": raw.get("allowedViewerState", 0),
        }

    @staticmethod
    def _normalize_post(raw: dict) -> dict:
        return {
            "id": raw.get("id"),
            "parent_id": raw.get("parentId", 0),
            "board_id": raw.get("boardId"),
            "user_id": raw.get("userId"),
            "user_name": raw.get("userName", ""),
            "time": raw.get("time", ""),
            "title": raw.get("title"),
            "content": raw.get("content", ""),
            "like_count": raw.get("likeCount", 0),
            "dislike_count": raw.get("dislikeCount", 0),
            "is_anonymous": raw.get("isAnonymous", False),
        }

    async def get_hot_topics(self, period: str) -> list[dict]:
        period_map = {
            "weekly": "/topic/hot-weekly",
            "monthly": "/topic/hot-monthly",
            "history": "/topic/hot-history",
        }
        path = period_map.get(period)
        if not path:
            raise RuntimeError(f"不支持的热门周期: {period}")
        data = await self._request_json("GET", path)
        return [self._normalize_topic_summary(item) for item in data]

    async def search_topics(
        self,
        keyword: str,
        *,
        from_offset: int = 0,
        size: int = 10,
        board_id: int = 0,
        credentials: dict | None = None,
    ) -> list[dict]:
        if not keyword.strip():
            raise RuntimeError("搜索关键词不能为空。")
        path = self._build_search_path(keyword, from_offset=from_offset, size=size, board_id=board_id)
        data = await self._request_json("GET", path, auth_required=True, credentials=credentials)
        return [self._normalize_topic_summary(item) for item in data]

    async def get_topic(self, topic_id: str | int, *, credentials: dict | None = None) -> dict:
        try:
            data = await self._request_json("GET", f"/topic/{topic_id}")
        except RuntimeError:
            data = await self._request_json("GET", f"/topic/{topic_id}", auth_required=True, credentials=credentials)
        return self._normalize_topic_detail(data)

    async def get_posts(
        self,
        topic_id: str | int,
        *,
        from_offset: int = 0,
        size: int = 10,
        credentials: dict | None = None,
    ) -> list[dict]:
        path = f"/Topic/{topic_id}/post?from={from_offset}&size={size}"
        try:
            data = await self._request_json("GET", path)
        except RuntimeError:
            data = await self._request_json("GET", path, auth_required=True, credentials=credentials)
        return [self._normalize_post(item) for item in data]

    async def get_hot_posts(self, topic_id: str | int, *, credentials: dict | None = None) -> list[dict]:
        path = f"/Topic/{topic_id}/hot-post"
        try:
            data = await self._request_json("GET", path)
        except RuntimeError:
            data = await self._request_json("GET", path, auth_required=True, credentials=credentials)
        return [self._normalize_post(item) for item in data]


def build_cc98_api(*, use_webvpn: bool = False) -> CC98Api:
    session = load_cc98_session()
    webvpn = restore_webvpn() if use_webvpn else None
    if use_webvpn and not webvpn:
        raise RuntimeError("未找到 WebVPN 会话。请先运行 python scripts/zju_login.py --webvpn")
    return CC98Api(
        access_token=session.get("access_token", ""),
        refresh_token=session.get("refresh_token", ""),
        expires_at=int(session.get("expires_at", 0) or 0),
        webvpn=webvpn,
    )


def emit_cc98_success(feature: str, data, *, meta: dict | None = None, source: str = "live"):
    emit_success(
        platform="cc98",
        feature=feature,
        data=data,
        meta=meta,
        source=source,
    )


def _add_webvpn_argument(parser: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
    kwargs = {}
    if suppress_default:
        kwargs["default"] = argparse.SUPPRESS
    parser.add_argument("--webvpn", action="store_true", help="通过当前 ZJU WebVPN 会话访问", **kwargs)


async def cmd_login(username: str, password: str, *, use_webvpn: bool = False, save_only: bool = False):
    save_cc98_credentials(username, password)
    if save_only:
        emit_cc98_success("login", {"saved": True}, meta={"login": False})
        return

    api = build_cc98_api(use_webvpn=use_webvpn)
    payload = await api.login(username, password)
    save_cc98_session(
        {
            "access_token": payload.get("access_token", ""),
            "refresh_token": payload.get("refresh_token", ""),
            "expires_at": api.expires_at,
            "token_type": payload.get("token_type", "Bearer"),
        }
    )
    emit_cc98_success(
        "login",
        {
            "logged_in": True,
            "expires_at": api.expires_at,
            "has_refresh_token": bool(payload.get("refresh_token")),
        },
        meta={"use_webvpn": use_webvpn},
    )


async def cmd_status():
    credentials = load_cc98_credentials()
    session = load_cc98_session()
    emit_cc98_success(
        "status",
        {
            "has_credentials": bool(credentials.get("username") and credentials.get("password")),
            "has_access_token": bool(session.get("access_token")),
            "has_refresh_token": bool(session.get("refresh_token")),
            "expires_at": int(session.get("expires_at", 0) or 0),
            "expired": _token_expired(int(session.get("expires_at", 0) or 0)),
        },
    )


async def cmd_hot(period: str, *, use_webvpn: bool = False):
    api = build_cc98_api(use_webvpn=use_webvpn)
    data = await api.get_hot_topics(period)
    emit_cc98_success("hot_topics", data, meta={"period": period, "use_webvpn": use_webvpn})


async def cmd_search(keyword: str, from_offset: int, size: int, board_id: int, *, use_webvpn: bool = False):
    api = build_cc98_api(use_webvpn=use_webvpn)
    credentials = load_cc98_credentials()
    data = await api.search_topics(
        keyword,
        from_offset=from_offset,
        size=size,
        board_id=board_id,
        credentials=credentials,
    )
    save_cc98_session(
        {
            "access_token": api.access_token,
            "refresh_token": api.refresh_token,
            "expires_at": api.expires_at,
            "token_type": "Bearer",
        }
    )
    emit_cc98_success(
        "search_topics",
        data,
        meta={
            "keyword": keyword,
            "from": from_offset,
            "size": size,
            "board_id": board_id,
            "use_webvpn": use_webvpn,
        },
    )


async def cmd_topic(topic_id: str, *, use_webvpn: bool = False):
    api = build_cc98_api(use_webvpn=use_webvpn)
    credentials = load_cc98_credentials()
    data = await api.get_topic(topic_id, credentials=credentials)
    emit_cc98_success("topic_detail", data, meta={"topic_id": topic_id, "use_webvpn": use_webvpn})


async def cmd_posts(topic_id: str, from_offset: int, size: int, *, use_webvpn: bool = False):
    api = build_cc98_api(use_webvpn=use_webvpn)
    credentials = load_cc98_credentials()
    data = await api.get_posts(topic_id, from_offset=from_offset, size=size, credentials=credentials)
    emit_cc98_success(
        "topic_posts",
        data,
        meta={"topic_id": topic_id, "from": from_offset, "size": size, "use_webvpn": use_webvpn},
    )


async def cmd_hot_posts(topic_id: str, *, use_webvpn: bool = False):
    api = build_cc98_api(use_webvpn=use_webvpn)
    credentials = load_cc98_credentials()
    data = await api.get_hot_posts(topic_id, credentials=credentials)
    emit_cc98_success("hot_posts", data, meta={"topic_id": topic_id, "use_webvpn": use_webvpn})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CC98 论坛工具")
    parser.set_defaults(webvpn=False)
    _add_webvpn_argument(parser, suppress_default=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="登录 CC98 并保存 token")
    _add_webvpn_argument(p_login, suppress_default=True)
    p_login.add_argument("--username", required=True, help="CC98 用户名")
    p_login.add_argument("--password", required=True, help="CC98 密码")
    p_login.add_argument("--save-only", action="store_true", help="仅保存凭证，不请求 token")

    p_status = sub.add_parser("status", help="查看 CC98 登录状态")
    _add_webvpn_argument(p_status, suppress_default=True)

    p_hot = sub.add_parser("hot", help="热门帖子")
    _add_webvpn_argument(p_hot, suppress_default=True)
    p_hot.add_argument("--period", default="weekly", choices=["weekly", "monthly", "history"], help="热门周期")

    p_search = sub.add_parser("search", help="搜索帖子")
    _add_webvpn_argument(p_search, suppress_default=True)
    p_search.add_argument("--keyword", required=True, help="搜索关键词")
    p_search.add_argument("--from", dest="from_offset", type=int, default=0, help="偏移量")
    p_search.add_argument("--size", type=int, default=10, help="返回数量")
    p_search.add_argument("--board-id", type=int, default=0, help="可选版面 ID")

    p_topic = sub.add_parser("topic", help="查看帖子详情")
    _add_webvpn_argument(p_topic, suppress_default=True)
    p_topic.add_argument("--topic-id", required=True, help="帖子 ID")

    p_posts = sub.add_parser("posts", help="查看帖子楼层")
    _add_webvpn_argument(p_posts, suppress_default=True)
    p_posts.add_argument("--topic-id", required=True, help="帖子 ID")
    p_posts.add_argument("--from", dest="from_offset", type=int, default=0, help="偏移量")
    p_posts.add_argument("--size", type=int, default=10, help="返回数量")

    p_hot_posts = sub.add_parser("hot-posts", help="查看热门回帖")
    _add_webvpn_argument(p_hot_posts, suppress_default=True)
    p_hot_posts.add_argument("--topic-id", required=True, help="帖子 ID")

    return parser


def main():
    parser = build_parser()

    args = parser.parse_args()

    try:
        if args.command == "login":
            asyncio.run(
                cmd_login(
                    args.username,
                    args.password,
                    use_webvpn=args.webvpn,
                    save_only=args.save_only,
                )
            )
        elif args.command == "status":
            asyncio.run(cmd_status())
        elif args.command == "hot":
            asyncio.run(cmd_hot(args.period, use_webvpn=args.webvpn))
        elif args.command == "search":
            asyncio.run(
                cmd_search(
                    args.keyword,
                    args.from_offset,
                    args.size,
                    args.board_id,
                    use_webvpn=args.webvpn,
                )
            )
        elif args.command == "topic":
            asyncio.run(cmd_topic(args.topic_id, use_webvpn=args.webvpn))
        elif args.command == "posts":
            asyncio.run(cmd_posts(args.topic_id, args.from_offset, args.size, use_webvpn=args.webvpn))
        elif args.command == "hot-posts":
            asyncio.run(cmd_hot_posts(args.topic_id, use_webvpn=args.webvpn))
    except RuntimeError as exc:
        emit_error(message=str(exc), platform="cc98", feature=args.command)
    except Exception as exc:
        emit_error(message=str(exc) or exc.__class__.__name__, platform="cc98", feature=args.command)


if __name__ == "__main__":
    main()
