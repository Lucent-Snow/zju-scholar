"""zju_zhiyun.py — 智云课堂 API + CLI

作为库: 提供 ZhiyunApi 类
作为脚本:
  python zju_zhiyun.py search --teacher 张三           # 按教师搜索
  python zju_zhiyun.py search --keyword 数据科学       # 按关键词搜索
  python zju_zhiyun.py subtitle --sub-id 12345         # 获取指定字幕
  python zju_zhiyun.py lecture --course 数据科学        # 一键获取讲座内容
  python zju_zhiyun.py lecture --course 数据科学 --teacher 张三 --index 0
"""

import httpx

URL_SEARCH = "https://classroom.zju.edu.cn/pptnote/v1/searchlist"
URL_DETAIL = "https://yjapi.cmc.zju.edu.cn/courseapi/v3/multi-search/get-course-detail"
URL_TRANS = "https://yjapi.cmc.zju.edu.cn/courseapi/v3/web-socket/search-trans-result"

DEFAULT_TENANT_ID = "112"
DEFAULT_PER_PAGE = 16
DEFAULT_TENANT_CODE = "112"


class ZhiyunApi:
    """智云课堂 API client."""

    def __init__(
        self,
        jwt: str,
        student_id: str = "",
        user_id: str = "",
        timeout: float = 8.0,
        webvpn=None,
    ):
        self.jwt = jwt
        self.student_id = student_id
        self.user_id = user_id
        self.timeout = timeout
        self._webvpn = webvpn
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Authorization": f"Bearer {jwt}" if not jwt.startswith("Bearer ") else jwt,
        }

    def _url(self, url: str) -> str:
        if self._webvpn and self._webvpn.logged_in:
            from zju_webvpn import convert_url
            return convert_url(url)
        return url

    def _make_client(self, **kwargs) -> httpx.AsyncClient:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", True)
        if self._webvpn and self._webvpn.logged_in:
            return self._webvpn.make_client(**kwargs)
        return httpx.AsyncClient(**kwargs)

    async def search_courses(
        self,
        teacher_name: str = "",
        keyword: str = "",
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[dict]:
        """搜索智云课程。可按老师名或关键词搜索。

        Returns list of {course_id, title, term, teacher, college}
        """
        params = {
            "tenant_id": DEFAULT_TENANT_ID,
            "page": page,
            "per_page": per_page,
            "tenant_code": DEFAULT_TENANT_CODE,
        }
        if teacher_name:
            params["realname"] = teacher_name
        if keyword:
            params["keyword"] = keyword
        if self.student_id:
            params["user_name"] = self.student_id
        if self.user_id:
            params["user_id"] = self.user_id

        all_courses = []

        async with self._make_client() as client:
            current_page = page
            while True:
                params["page"] = current_page
                resp = await client.get(self._url(URL_SEARCH), headers=self._headers, params=params)
                data = resp.json()

                raw_list = []
                if "data" in data and "list" in data["data"]:
                    raw_list = data["data"]["list"]
                elif isinstance(data.get("total"), dict):
                    raw_list = data["total"].get("list", [])

                if not raw_list:
                    break

                for item in raw_list:
                    all_courses.append({
                        "course_id": item.get("course_id"),
                        "title": item.get("title", "未知课程"),
                        "term": item.get("term_name", "未知学期"),
                        "teacher": item.get("lecturer_name", item.get("realname", "")),
                        "college": item.get("kkxy_name", ""),
                    })

                if len(raw_list) < per_page:
                    break
                current_page += 1

        return all_courses

    async def get_course_detail(self, course_id: int | str, teacher_name: str = "") -> list[dict]:
        """获取课程视频列表。只返回 sub_status=6 (有字幕) 的视频。

        Returns list of {sub_id, sub_title, lecturer_name}
        """
        params = {
            "course_id": str(course_id),
        }
        if self.student_id:
            params["student"] = self.student_id

        headers = self._headers.copy()
        headers["Referer"] = (
            f"https://classroom.zju.edu.cn/coursedetail?course_id={course_id}&tenant_code=112"
        )

        async with self._make_client() as client:
            resp = await client.get(self._url(URL_DETAIL), headers=headers, params=params)
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取课程详情失败: {data.get('msg', 'unknown error')}")

        course_data = data.get("data", {})
        sub_list_raw = course_data.get("sub_list", {})

        valid_subs = []

        def extract_videos(obj):
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict) and "sub_title" in item:
                        sub_status = str(item.get("sub_status", ""))
                        if sub_status != "6":
                            continue
                        lecturer = item.get("lecturer_name", "")
                        if teacher_name and teacher_name not in lecturer:
                            continue
                        valid_subs.append({
                            "sub_id": item["id"],
                            "sub_title": item["sub_title"],
                            "lecturer_name": lecturer,
                        })
            elif isinstance(obj, dict):
                for value in obj.values():
                    extract_videos(value)

        extract_videos(sub_list_raw)
        return valid_subs

    async def get_transcript(self, sub_id: int | str) -> dict | None:
        """获取字幕 JSON 数据。"""
        params = {
            "sub_id": str(sub_id),
            "format": "json",
        }
        headers = self._headers.copy()
        headers["Referer"] = f"https://classroom.zju.edu.cn/livingroom?sub_id={sub_id}"

        async with self._make_client() as client:
            resp = await client.get(self._url(URL_TRANS), headers=headers, params=params)

        if resp.status_code != 200:
            return None

        try:
            data = resp.json()
        except Exception:
            return None

        # Check for valid transcript data
        if "list" in data and data["list"]:
            return data
        if "data" in data and isinstance(data["data"], dict):
            if "list" in data["data"] and data["data"]["list"]:
                return data

        return None

    async def get_subtitle_text(self, sub_id: int | str) -> str | None:
        """获取纯文本字幕（带时间戳）。"""
        transcript = await self.get_transcript(sub_id)
        if not transcript:
            return None

        segments = transcript.get("list", [])
        if not segments and "data" in transcript:
            segments = transcript.get("data", {}).get("list", [])

        if not segments:
            return None

        lines = []
        for seg in segments:
            start_ms = seg.get("start_time", seg.get("startTime", 0))
            text = seg.get("text", seg.get("content", ""))
            if text:
                minutes = int(start_ms) // 60000
                seconds = (int(start_ms) % 60000) // 1000
                lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

        return "\n".join(lines) if lines else None


# --- CLI ---

def _get_api():
    import json, sys
    from pathlib import Path

    SKILL_DIR = Path(__file__).resolve().parent.parent
    SESSION_FILE = SKILL_DIR / "data" / "session.json"
    CRED_FILE = SKILL_DIR / "data" / "credentials.json"

    jwt = None
    student_id = ""
    webvpn = None

    if SESSION_FILE.exists():
        try:
            session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            jwt = session.get("zhiyun_jwt")
            student_id = session.get("username", "")
            # 恢复 WebVPN 状态
            if session.get("webvpn_enabled") and session.get("webvpn_cookies"):
                from zju_webvpn import WebVpnSession
                webvpn = WebVpnSession()
                webvpn.cookies = session["webvpn_cookies"]
                webvpn.logged_in = True
        except (json.JSONDecodeError, OSError):
            pass

    if not jwt and CRED_FILE.exists():
        try:
            cred = json.loads(CRED_FILE.read_text(encoding="utf-8"))
            jwt = cred.get("zhiyun_token")
            student_id = student_id or cred.get("username", "")
        except (json.JSONDecodeError, OSError):
            pass

    if not jwt:
        print("错误: 未设置智云 JWT。请先运行 python zju_login.py 或通过 --zhiyun-token 设置。", file=sys.stderr)
        sys.exit(1)

    return ZhiyunApi(jwt=jwt, student_id=student_id, webvpn=webvpn)


async def _cmd_search(teacher_name: str = "", keyword: str = ""):
    import json
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()

    cache_key = CacheManager.make_search_key(teacher_name, keyword)
    cached = cache.get(cache_key, "zhiyun_search")
    if cached:
        print(json.dumps(cached, ensure_ascii=False, indent=2))
        return

    courses = await api.search_courses(teacher_name=teacher_name, keyword=keyword)
    cache.set(cache_key, courses, "zhiyun_search")
    print(json.dumps(courses, ensure_ascii=False, indent=2))


async def _cmd_subtitle(sub_id: str):
    import json
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()

    cache_key = f"zhiyun_transcript_{sub_id}"
    cached = cache.get(cache_key, "zhiyun_transcript")
    if cached:
        print(cached if isinstance(cached, str) else json.dumps(cached, ensure_ascii=False))
        return

    text = await api.get_subtitle_text(sub_id)
    if text:
        cache.set(cache_key, text, "zhiyun_transcript")
        print(text)
    else:
        print(f"未找到 sub_id={sub_id} 的字幕，可能该视频尚未转录。")


async def _cmd_lecture(course_name: str, teacher_name: str = "", lecture_index: int = 0):
    import json
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()

    # Step 1: 搜索课程
    courses = await api.search_courses(
        teacher_name=teacher_name,
        keyword=course_name if not teacher_name else "",
    )

    matching = [c for c in courses if course_name in c.get("title", "")]
    if not matching:
        matching = courses
    if not matching:
        print(f"未找到与 '{course_name}' 相关的智云课程。")
        return

    # Step 2: 获取视频列表
    course = matching[0]
    videos = await api.get_course_detail(course["course_id"], teacher_name=teacher_name)

    if not videos:
        print(f"课程《{course['title']}》({course['term']}) 没有可用的字幕视频。")
        return

    idx = min(lecture_index, len(videos) - 1)
    target = videos[idx]

    # Step 3: 获取字幕
    text = await api.get_subtitle_text(target["sub_id"])

    if not text:
        print(f"课程《{course['title']}》的视频「{target['sub_title']}」暂无可用字幕。")
        print(f"\n该课程共有 {len(videos)} 个有字幕的视频:")
        for i, v in enumerate(videos):
            print(f"  [{i}] {v['sub_title']}")
        return

    cache.set(f"zhiyun_transcript_{target['sub_id']}", text, "zhiyun_transcript")

    print(f"课程: {course['title']} ({course['term']})")
    print(f"讲座: {target['sub_title']}")
    print(f"教师: {target.get('lecturer_name', teacher_name)}")
    print("---\n")
    print(text)


def main():
    import argparse
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    parser = argparse.ArgumentParser(description="智云课堂工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="搜索智云课程")
    p_search.add_argument("--teacher", default="", help="教师姓名")
    p_search.add_argument("--keyword", default="", help="搜索关键词")

    p_sub = sub.add_parser("subtitle", help="获取指定视频字幕")
    p_sub.add_argument("--sub-id", required=True, help="视频/子课程 ID")

    p_lec = sub.add_parser("lecture", help="一键获取讲座内容")
    p_lec.add_argument("--course", required=True, help="课程名称")
    p_lec.add_argument("--teacher", default="", help="教师姓名（可选）")
    p_lec.add_argument("--index", type=int, default=0, help="讲座索引，0=最新（默认 0）")

    args = parser.parse_args()

    try:
        if args.command == "search":
            if not args.teacher and not args.keyword:
                print("错误: 请至少提供 --teacher 或 --keyword", file=sys.stderr)
                sys.exit(1)
            asyncio.run(_cmd_search(args.teacher, args.keyword))
        elif args.command == "subtitle":
            asyncio.run(_cmd_subtitle(args.sub_id))
        elif args.command == "lecture":
            asyncio.run(_cmd_lecture(args.course, args.teacher, args.index))
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
