"""zju_zhiyun.py — 智云课堂 API + CLI

作为库: 提供 ZhiyunApi 类
作为脚本:
  python zju_zhiyun.py my-courses --keyword 数据科学    # 默认推荐：从“我的课程”定位课程
  python zju_zhiyun.py search --teacher 张三           # 可选：全站搜索（当前平台下可能为空）
  python zju_zhiyun.py subtitle --sub-id 12345         # 默认输出纯文本字幕
  python zju_zhiyun.py lecture --course 数据科学        # 一键获取讲座纯文本
"""

from collections import OrderedDict

import httpx
import re
import json

URL_SEARCH = "https://classroom.zju.edu.cn/pptnote/v1/searchlist"
URL_DETAIL = "https://yjapi.cmc.zju.edu.cn/courseapi/v3/multi-search/get-course-detail"
URL_CATALOGUE = "https://yjapi.cmc.zju.edu.cn/courseapi/v2/course/catalogue"
URL_TRANS = "https://yjapi.cmc.zju.edu.cn/courseapi/v3/web-socket/search-trans-result"
URL_PPT = "https://classroom.zju.edu.cn/pptnote/v1/schedule/search-ppt"
URL_MY_COURSES = (
    "https://education.cmc.zju.edu.cn/personal/courseapi/"
    "vlabpassportapi/v1/account-profile/course"
)
URL_MY_STUDY = (
    "https://education.cmc.zju.edu.cn/personal/courseapi/"
    "vlabpassportapi/v1/account-profile/study"
)

DEFAULT_TENANT_ID = "112"
DEFAULT_PER_PAGE = 16
DEFAULT_TENANT_CODE = "112"
FILLER_PREFIX_RE = re.compile(r"^(?:嗯+|啊+|呃+|额+|噢+|哦+|哎+|诶+|欸+)[，。！？；：、,.!?;:\s]*")
LOW_INFORMATION_TEXTS = {
    "嗯",
    "啊",
    "呃",
    "额",
    "哦",
    "噢",
    "哎",
    "诶",
    "欸",
    "是",
    "对",
    "行",
    "到",
    "我",
    "你",
    "他",
    "她",
    "它",
    "这个",
    "那个",
    "没有",
    "不是",
    "什么",
    "感觉",
}


class ZhiyunApi:
    """智云课堂 API client."""

    def __init__(
        self,
        jwt: str,
        student_id: str = "",
        user_id: str = "",
        timeout: float = 15.0,
        webvpn=None,
    ):
        self.jwt = jwt
        self.student_id = student_id
        self.user_id = str(user_id or self._extract_user_id_from_jwt(jwt) or "")
        self.timeout = timeout
        self._webvpn = webvpn
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Authorization": f"Bearer {jwt}" if not jwt.startswith("Bearer ") else jwt,
        }

    @staticmethod
    def _extract_user_id_from_jwt(jwt: str) -> str:
        import base64
        import json

        token = jwt.split(" ", 1)[-1] if jwt.startswith("Bearer ") else jwt
        parts = token.split(".")
        if len(parts) < 2:
            return ""

        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except Exception:
            return ""

        user_id = claims.get("sub")
        return str(user_id) if user_id is not None else ""

    @staticmethod
    def _course_matches(course: dict, keyword: str = "", teacher_name: str = "") -> bool:
        title = course.get("title", "")
        teacher = course.get("teacher", "")
        if keyword and keyword not in title:
            return False
        if teacher_name and teacher_name not in teacher:
            return False
        return True

    @staticmethod
    def _parse_course_information(raw: dict) -> dict:
        import json

        info = raw.get("information", {})
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except Exception:
                info = {}
        return info if isinstance(info, dict) else {}

    def _normalize_my_course(self, raw: dict) -> dict:
        info = self._parse_course_information(raw)

        teachers = raw.get("Teachers") or raw.get("teachers") or []
        teacher_names = []
        for item in teachers:
            if not isinstance(item, dict):
                continue
            name = item.get("Realname") or item.get("realname") or ""
            if name:
                teacher_names.append(name)

        teacher = (
            ",".join(teacher_names)
            or raw.get("Teacher")
            or raw.get("teacher_search")
            or raw.get("realname")
            or ""
        )

        return {
            "course_id": raw.get("Id") or raw.get("id"),
            "title": raw.get("Title") or raw.get("title", "未知课程"),
            "term": raw.get("TermName") or raw.get("term_name", "未知学期"),
            "teacher": teacher,
            "college": raw.get("KkxyName") or raw.get("kkxy_name", ""),
            "course_code": info.get("kcdm", ""),
            "course_key": info.get("kcwybm", ""),
            "prev_sub_id": raw.get("PrevSubjectId") or raw.get("course_subject_id") or 0,
            "progress": raw.get("progress", {}),
            "source": "my_courses",
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

    @staticmethod
    def _clean_text(text: str) -> str:
        if text is None:
            return ""
        text = str(text).replace("\r", " ").replace("\n", " ").strip()
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        if re.search(r"[\u4e00-\u9fff]", text):
            text = re.sub(r"\s+", "", text)
        return text.strip()

    @classmethod
    def _normalize_search_text(cls, text: str) -> str:
        return cls._text_core(cls._clean_text(text)).lower()

    @classmethod
    def _keyword_variants(cls, keyword: str) -> list[str]:
        base = cls._normalize_search_text(keyword)
        if not base:
            return []

        variants = OrderedDict()

        def add(value: str):
            value = cls._normalize_search_text(value)
            if len(value) >= 2:
                variants[value] = None

        add(base)
        if len(base) >= 4:
            add(base[:4])
            add(base[-4:])
        if len(base) >= 3:
            add(base[:3])
            add(base[-3:])
        if len(base) >= 2:
            add(base[:2])
            add(base[-2:])
        if len(base) <= 8:
            for size in range(min(4, len(base)), 1, -1):
                for start in range(0, len(base) - size + 1):
                    add(base[start:start + size])

        return list(variants.keys())

    def _normalize_search_result(self, item: dict) -> dict:
        return {
            "course_id": item.get("course_id"),
            "title": item.get("title", "未知课程"),
            "term": item.get("term_name", item.get("term", "未知学期")),
            "teacher": item.get("lecturer_name", item.get("realname", item.get("teacher", ""))),
            "college": item.get("kkxy_name", item.get("college", "")),
            "subject_title": item.get("subject_title", ""),
        }

    @classmethod
    def _search_result_matches(
        cls,
        course: dict,
        *,
        keyword: str = "",
        teacher_name: str = "",
    ) -> bool:
        if teacher_name:
            teacher_norm = cls._normalize_search_text(course.get("teacher", ""))
            if cls._normalize_search_text(teacher_name) not in teacher_norm:
                return False

        if keyword:
            keyword_norm = cls._normalize_search_text(keyword)
            haystacks = [
                cls._normalize_search_text(course.get("title", "")),
                cls._normalize_search_text(course.get("subject_title", "")),
                cls._normalize_search_text(course.get("teacher", "")),
                cls._normalize_search_text(course.get("college", "")),
            ]
            if not any(keyword_norm and keyword_norm in text for text in haystacks if text):
                return False

        return True

    async def _search_courses_once(
        self,
        *,
        teacher_name: str = "",
        keyword: str = "",
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = 8,
    ) -> list[dict]:
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

        if not params.get("user_name") or not params.get("user_id"):
            raise RuntimeError("智云 search 缺少 user_name/user_id，无法发起搜索。")

        all_courses = []

        async with self._make_client() as client:
            current_page = page
            while current_page < page + max_pages:
                params["page"] = current_page
                resp = await client.get(self._url(URL_SEARCH), headers=self._headers, params=params)
                data = resp.json()

                if data.get("code") not in (None, 0):
                    raise RuntimeError(f"智云 search 失败: {data.get('msg', 'unknown error')}")

                raw_list = []
                if "data" in data and "list" in data["data"]:
                    raw_list = data["data"]["list"]
                elif isinstance(data.get("total"), dict):
                    raw_list = data["total"].get("list", [])

                if not raw_list:
                    break

                all_courses.extend(self._normalize_search_result(item) for item in raw_list)

                if len(raw_list) < per_page:
                    break
                current_page += 1

        return all_courses

    @staticmethod
    def _strip_leading_fillers(text: str) -> str:
        previous = None
        while text and text != previous:
            previous = text
            text = FILLER_PREFIX_RE.sub("", text).strip()
        return text

    @staticmethod
    def _text_core(text: str) -> str:
        return re.sub(r"[，。！？；：、,.!?;:（）()\[\]{}\"'“”‘’·\-\s]", "", text)

    @classmethod
    def _is_low_information_text(cls, text: str) -> bool:
        core = cls._text_core(text)
        if not core:
            return True
        if core.isdigit():
            return True
        if core in LOW_INFORMATION_TEXTS:
            return True
        if len(core) <= 2 and all(ch in "嗯啊呃额哦噢哎诶欸哈呀" for ch in core):
            return True
        return False

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
        variants = self._keyword_variants(keyword) if keyword else [""]
        if not variants:
            variants = [keyword]

        dedup: OrderedDict[str, dict] = OrderedDict()
        for variant in variants:
            raw_courses = await self._search_courses_once(
                teacher_name=teacher_name,
                keyword=variant,
                page=page,
                per_page=per_page,
            )
            for course in raw_courses:
                if not self._search_result_matches(course, keyword=variant, teacher_name=teacher_name):
                    continue
                key = f"{course.get('course_id')}|{course.get('title', '')}|{course.get('teacher', '')}"
                dedup.setdefault(key, course)

            if dedup:
                break

        return sorted(
            dedup.values(),
            key=lambda item: int(item.get("course_id") or 0),
            reverse=True,
        )

    async def get_my_courses(
        self,
        keyword: str = "",
        teacher_name: str = "",
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict]:
        """获取当前账号的课程列表，比全站搜索更适合拿课程 ID。"""
        params = {
            "nowpage": page,
            "per-page": per_page,
            "force_mycourse": 0,
        }
        headers = self._headers.copy()
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = "https://education.cmc.zju.edu.cn/personal/"

        all_courses = []

        async with self._make_client() as client:
            current_page = page
            while True:
                params["nowpage"] = current_page
                resp = await client.get(self._url(URL_MY_COURSES), headers=headers, params=params)
                data = resp.json()

                raw_result = data.get("params", {}).get("result", {})
                raw_list = raw_result.get("data", []) or raw_result.get("models", [])
                if not raw_list:
                    break

                normalized = [self._normalize_my_course(item) for item in raw_list]
                all_courses.extend(
                    course
                    for course in normalized
                    if self._course_matches(course, keyword=keyword, teacher_name=teacher_name)
                )

                if len(raw_list) < per_page:
                    break
                current_page += 1

        return all_courses

    async def get_recent_learning(self, per_page: int = 10) -> list[dict]:
        """获取最近学习，用于更快定位近期课程和最近的 sub_id。"""
        params = {
            "nowpage": 1,
            "per-page": per_page,
        }
        headers = self._headers.copy()
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = "https://education.cmc.zju.edu.cn/personal/"

        async with self._make_client() as client:
            resp = await client.get(self._url(URL_MY_STUDY), headers=headers, params=params)
            data = resp.json()

        raw_result = data.get("params", {}).get("result", {})
        raw_list = raw_result.get("models", []) or raw_result.get("data", [])

        results = []
        for item in raw_list:
            results.append({
                "course_id": item.get("id"),
                "title": item.get("title", "未知课程"),
                "teacher": item.get("realname", ""),
                "term": item.get("term_name", ""),
                "sub_id": item.get("course_subject_id"),
                "updated_at": item.get("record_update") or item.get("updated_at", ""),
                "source": "recent_learning",
            })

        return results

    @staticmethod
    def _parse_embedded_json(raw):
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def get_course_videos(
        self,
        course_id: int | str,
        *,
        teacher_name: str = "",
        with_subtitles_only: bool = False,
    ) -> list[dict]:
        headers = self._headers.copy()
        headers["Referer"] = (
            f"https://classroom.zju.edu.cn/coursedetail?course_id={course_id}&tenant_code=112"
        )

        async with self._make_client() as client:
            resp = await client.get(
                self._url(URL_CATALOGUE),
                headers=headers,
                params={"course_id": str(course_id)},
            )
            data = resp.json()

        raw_list = data.get("result", {}).get("data", []) or data.get("data", [])
        videos = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            lecturer = item.get("lecturer_name", "") or item.get("realname", "")
            if teacher_name and teacher_name not in lecturer:
                continue

            status = str(item.get("status", item.get("sub_status", "")))
            if with_subtitles_only and status != "6":
                continue

            content = self._parse_embedded_json(item.get("content"))
            playback = content.get("playback", {}) if isinstance(content, dict) else {}

            videos.append(
                {
                    "course_id": item.get("course_id", course_id),
                    "sub_id": item.get("sub_id") or item.get("id"),
                    "title": item.get("title") or item.get("sub_title", "未知视频"),
                    "lecturer_name": lecturer,
                    "status": status,
                    "start_at": item.get("start_at", ""),
                    "end_at": item.get("end_at", ""),
                    "duration": item.get("duration", 0),
                    "playback_url": playback.get("url", ""),
                    "has_subtitle": status == "6",
                    "raw": item,
                }
            )

        videos.sort(key=lambda item: int(item.get("sub_id") or 0), reverse=True)
        return videos

    async def get_ppt_timeline(
        self,
        course_id: int | str,
        sub_id: int | str,
        *,
        per_page: int = 100,
    ) -> list[dict]:
        headers = self._headers.copy()
        headers["Referer"] = f"https://classroom.zju.edu.cn/livingroom?sub_id={sub_id}"

        timeline = []
        async with self._make_client() as client:
            page = 1
            while True:
                resp = await client.get(
                    self._url(URL_PPT),
                    headers=headers,
                    params={
                        "course_id": str(course_id),
                        "sub_id": str(sub_id),
                        "page": page,
                        "per_page": per_page,
                    },
                )
                data = resp.json()
                raw_list = data.get("list", [])
                if not raw_list:
                    break

                for item in raw_list:
                    content = self._parse_embedded_json(item.get("content"))
                    timeline.append(
                        {
                            "course_id": str(course_id),
                            "sub_id": str(sub_id),
                            "slide_id": item.get("id"),
                            "created_sec": int(item.get("created_sec", 0) or 0),
                            "image_url": content.get("pptimgurl", ""),
                            "title": content.get("title", ""),
                            "raw": item,
                        }
                    )

                if len(raw_list) < per_page:
                    break
                page += 1

        timeline.sort(key=lambda item: item["created_sec"])
        return timeline

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
        valid_subs.sort(key=lambda item: int(item.get("sub_id", 0)), reverse=True)
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

    @staticmethod
    def _extract_transcript_segments(transcript: dict | None) -> list[dict]:
        if not transcript:
            return []
        segments = transcript.get("list", [])
        if not segments and "data" in transcript:
            segments = transcript.get("data", {}).get("list", [])

        # 某些智云字幕接口会返回 list=[{all_content:[...]}]
        if segments and isinstance(segments, list):
            first = segments[0]
            if isinstance(first, dict) and isinstance(first.get("all_content"), list):
                segments = first["all_content"]

        return segments if isinstance(segments, list) else []

    @classmethod
    def _normalize_transcript_segments(
        cls,
        transcript: dict | None,
        include_translation: bool = False,
    ) -> list[dict]:
        normalized = []
        last_text = None
        for seg in cls._extract_transcript_segments(transcript):
            start_raw = seg.get(
                "start_time",
                seg.get("startTime", seg.get("BeginSec", 0)),
            )
            end_raw = seg.get(
                "end_time",
                seg.get("endTime", seg.get("EndSec", start_raw)),
            )
            text = cls._clean_text(seg.get("text", seg.get("content", seg.get("Text", ""))))
            translation = cls._clean_text(
                seg.get(
                    "translation",
                    seg.get("translate", seg.get("TransText", "")),
                )
            )
            if not text:
                continue
            if text == last_text:
                continue

            start_int = int(start_raw or 0)
            end_int = int(end_raw or start_raw or 0)
            if "BeginSec" in seg and "start_time" not in seg and "startTime" not in seg:
                start_sec = start_int
                end_sec = end_int
            else:
                start_sec = start_int // 1000
                end_sec = end_int // 1000

            item = {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "text": text,
            }
            if include_translation and translation:
                item["translation"] = translation

            normalized.append(item)
            last_text = text

        return normalized

    @staticmethod
    def _format_timestamp(total_seconds: int) -> str:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"[{minutes:02d}:{seconds:02d}]"

    @classmethod
    def format_subtitle_text(
        cls,
        transcript: dict | None,
        *,
        timestamps: bool = False,
        include_translation: bool = False,
        filter_fillers: bool = True,
    ) -> str | None:
        segments = cls._normalize_transcript_segments(
            transcript,
            include_translation=include_translation,
        )
        if not segments:
            return None

        if filter_fillers:
            filtered_segments = []
            for seg in segments:
                cleaned_text = cls._strip_leading_fillers(seg["text"])
                if cls._is_low_information_text(cleaned_text):
                    continue

                normalized_seg = dict(seg)
                normalized_seg["text"] = cleaned_text
                filtered_segments.append(normalized_seg)

            if filtered_segments:
                segments = filtered_segments

        if timestamps:
            lines = []
            for seg in segments:
                line = f"{cls._format_timestamp(seg['start_sec'])} {seg['text']}"
                if include_translation and seg.get("translation"):
                    line = f"{line}\n{seg['translation']}"
                lines.append(line)
            return "\n".join(lines) if lines else None

        paragraphs = []
        current = ""
        prev_end = None

        for seg in segments:
            text = seg["text"]
            gap = (seg["start_sec"] - prev_end) if prev_end is not None else 0
            should_break = (
                not current
                or gap >= 12
                or len(current) >= 180
                or (
                    current.endswith(("。", "！", "？", "；"))
                    and len(current) >= 60
                )
            )
            if should_break and current:
                paragraphs.append(current.strip())
                current = ""

            if current and not text.startswith(("，", "。", "！", "？", "；", "：", "、", ",", ".", "!", "?", ";", ":", ")", "）")):
                if re.search(r"[\u4e00-\u9fff]", current[-1] + text[:1]):
                    current += ""
                else:
                    current += " "
            current += text
            if include_translation and seg.get("translation"):
                current += f"\n{seg['translation']}"
            prev_end = seg["end_sec"] or seg["start_sec"]

        if current:
            paragraphs.append(current.strip())

        return "\n\n".join(paragraphs) if paragraphs else None

    async def get_subtitle_text(
        self,
        sub_id: int | str,
        *,
        timestamps: bool = False,
        include_translation: bool = False,
        filter_fillers: bool = True,
    ) -> str | None:
        """获取适合阅读的字幕文本，默认纯文本、默认不带翻译。"""
        transcript = await self.get_transcript(sub_id)
        return self.format_subtitle_text(
            transcript,
            timestamps=timestamps,
            include_translation=include_translation,
            filter_fillers=filter_fillers,
        )


# --- CLI ---

def _get_api():
    from zju_session import get_zhiyun_api

    return get_zhiyun_api()


async def _cmd_search(teacher_name: str = "", keyword: str = ""):
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()

    cache_key = CacheManager.make_search_key(teacher_name, keyword)
    cached = cache.get(cache_key, "zhiyun_search")
    if cached:
        _emit_zhiyun_success(
            "search_courses",
            cached,
            meta={"teacher": teacher_name, "keyword": keyword},
            source="cache",
        )
        return

    courses = await api.search_courses(teacher_name=teacher_name, keyword=keyword)
    cache.set(cache_key, courses, "zhiyun_search")
    _emit_zhiyun_success(
        "search_courses",
        courses,
        meta={"teacher": teacher_name, "keyword": keyword},
    )


async def _cmd_my_courses(teacher_name: str = "", keyword: str = ""):
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()

    cache_key = f"zhiyun_my_courses_{teacher_name}_{keyword or '__all__'}"
    cached = cache.get(cache_key, "zhiyun_my_courses")
    if cached:
        _emit_zhiyun_success(
            "my_courses",
            cached,
            meta={"teacher": teacher_name, "keyword": keyword},
            source="cache",
        )
        return

    courses = await api.get_my_courses(keyword=keyword, teacher_name=teacher_name)
    cache.set(cache_key, courses, "zhiyun_my_courses")
    _emit_zhiyun_success(
        "my_courses",
        courses,
        meta={"teacher": teacher_name, "keyword": keyword},
    )


def _make_transcript_cache_key(sub_id: str, timestamps: bool, include_translation: bool) -> str:
    return (
        f"zhiyun_transcript_v3_{sub_id}"
        f"_ts{int(timestamps)}"
        f"_tr{int(include_translation)}"
    )


async def _load_transcript_cached(api, cache, sub_id: str):
    raw_key = f"zhiyun_transcript_raw_{sub_id}"
    cached = cache.get(raw_key, "zhiyun_transcript")
    if cached:
        return cached

    transcript = await api.get_transcript(sub_id)
    if transcript:
        cache.set(raw_key, transcript, "zhiyun_transcript")
    return transcript


async def _resolve_course(api, *, course_name: str = "", teacher_name: str = "", course_id: str = "") -> dict | None:
    if course_id:
        return {"course_id": course_id, "title": course_name or "", "teacher": teacher_name or ""}

    recent_courses = await api.get_recent_learning(per_page=20)
    matching = [
        course
        for course in recent_courses
        if api._course_matches(course, keyword=course_name, teacher_name=teacher_name)
    ]
    if not matching:
        matching = await api.get_my_courses(keyword=course_name, teacher_name=teacher_name)
    return matching[0] if matching else None


def _emit_zhiyun_success(feature: str, data, *, meta: dict | None = None, source: str = "live"):
    from zju_output import emit_success

    emit_success(
        platform="zhiyun",
        feature=feature,
        data=data,
        meta=meta,
        source=source,
    )


async def _cmd_subtitle(
    sub_id: str,
    *,
    timestamps: bool = False,
    include_translation: bool = False,
    filter_fillers: bool = True,
):
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()

    cache_key = _make_transcript_cache_key(sub_id, timestamps, include_translation)
    cached = cache.get(cache_key, "zhiyun_transcript")
    if cached:
        _emit_zhiyun_success(
            "subtitle_text",
            {"sub_id": str(sub_id), "text": cached},
            meta={
                "sub_id": str(sub_id),
                "timestamps": timestamps,
                "include_translation": include_translation,
                "filter_fillers": filter_fillers,
            },
            source="cache",
        )
        return

    transcript = await _load_transcript_cached(api, cache, sub_id)
    text = api.format_subtitle_text(
        transcript,
        timestamps=timestamps,
        include_translation=include_translation,
        filter_fillers=filter_fillers,
    )
    if text:
        cache.set(cache_key, text, "zhiyun_transcript")
        _emit_zhiyun_success(
            "subtitle_text",
            {"sub_id": str(sub_id), "text": text},
            meta={
                "sub_id": str(sub_id),
                "timestamps": timestamps,
                "include_translation": include_translation,
                "filter_fillers": filter_fillers,
            },
        )
    else:
        _emit_zhiyun_success(
            "subtitle_text",
            {"sub_id": str(sub_id), "text": None},
            meta={
                "sub_id": str(sub_id),
                "timestamps": timestamps,
                "include_translation": include_translation,
                "filter_fillers": filter_fillers,
                "message": "未找到字幕，可能该视频尚未转录。",
            },
        )


async def _cmd_lecture(
    course_name: str,
    teacher_name: str = "",
    lecture_index: int = 0,
    *,
    timestamps: bool = False,
    include_translation: bool = False,
    filter_fillers: bool = True,
):
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()

    course = await _resolve_course(api, course_name=course_name, teacher_name=teacher_name)
    if not course:
        _emit_zhiyun_success(
            "lecture_text",
            {"course": course_name, "text": None},
            meta={"teacher": teacher_name, "message": "未在当前账号课程中找到该课程。"},
        )
        return
    videos = await api.get_course_detail(course["course_id"], teacher_name=teacher_name)

    if not videos:
        _emit_zhiyun_success(
            "lecture_text",
            {"course": course.get("title", course_name), "text": None},
            meta={"teacher": teacher_name, "message": "该课程没有可用的字幕视频。"},
        )
        return

    idx = min(lecture_index, len(videos) - 1)
    target = videos[idx]

    # Step 3: 获取字幕
    transcript = await _load_transcript_cached(api, cache, str(target["sub_id"]))
    text = api.format_subtitle_text(
        transcript,
        timestamps=timestamps,
        include_translation=include_translation,
        filter_fillers=filter_fillers,
    )

    if not text:
        _emit_zhiyun_success(
            "lecture_text",
            {
                "course": course.get("title", course_name),
                "target_video": target,
                "text": None,
                "available_videos": videos,
            },
            meta={"teacher": teacher_name, "index": lecture_index, "message": "目标视频暂无可用字幕。"},
        )
        return

    cache.set(
        _make_transcript_cache_key(target["sub_id"], timestamps, include_translation),
        text,
        "zhiyun_transcript",
    )
    _emit_zhiyun_success(
        "lecture_text",
        {
            "course": {
                "course_id": course.get("course_id"),
                "title": course.get("title", course_name),
                "term": course.get("term", ""),
            },
            "video": target,
            "text": text,
        },
        meta={
            "teacher": teacher_name,
            "index": lecture_index,
            "timestamps": timestamps,
            "include_translation": include_translation,
            "filter_fillers": filter_fillers,
        },
    )


async def _cmd_videos(course_name: str = "", teacher_name: str = "", course_id: str = "", with_all_status: bool = False):
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()
    course = await _resolve_course(api, course_name=course_name, teacher_name=teacher_name, course_id=course_id)
    if not course:
        _emit_zhiyun_success(
            "course_videos",
            [],
            meta={"course": course_name, "teacher": teacher_name, "message": "未找到课程。"},
        )
        return

    resolved_course_id = str(course.get("course_id"))
    cache_key = f"zhiyun_videos_{resolved_course_id}_{teacher_name}_{int(with_all_status)}"
    cached = cache.get(cache_key, "zhiyun_videos")
    if cached is not None:
        _emit_zhiyun_success(
            "course_videos",
            cached,
            meta={"course_id": resolved_course_id, "course": course_name, "teacher": teacher_name},
            source="cache",
        )
        return

    videos = await api.get_course_videos(
        resolved_course_id,
        teacher_name=teacher_name,
        with_subtitles_only=not with_all_status,
    )
    cache.set(cache_key, videos, "zhiyun_videos")
    _emit_zhiyun_success(
        "course_videos",
        videos,
        meta={"course_id": resolved_course_id, "course": course_name, "teacher": teacher_name},
    )


async def _cmd_ppt(
    *,
    course_name: str = "",
    teacher_name: str = "",
    course_id: str = "",
    sub_id: str = "",
    lecture_index: int = 0,
):
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()
    course = await _resolve_course(api, course_name=course_name, teacher_name=teacher_name, course_id=course_id)
    if not course:
        _emit_zhiyun_success(
            "ppt_timeline",
            [],
            meta={"course": course_name, "teacher": teacher_name, "message": "未找到课程。"},
        )
        return

    resolved_course_id = str(course.get("course_id"))
    resolved_sub_id = str(sub_id) if sub_id else ""
    if not resolved_sub_id:
        videos = await api.get_course_videos(resolved_course_id, teacher_name=teacher_name, with_subtitles_only=False)
        if not videos:
            _emit_zhiyun_success(
                "ppt_timeline",
                [],
                meta={"course_id": resolved_course_id, "message": "该课程没有可用视频。"},
            )
            return
        target = videos[min(lecture_index, len(videos) - 1)]
        resolved_sub_id = str(target["sub_id"])

    cache_key = f"zhiyun_ppt_{resolved_course_id}_{resolved_sub_id}"
    cached = cache.get(cache_key, "zhiyun_ppt")
    if cached is not None:
        _emit_zhiyun_success(
            "ppt_timeline",
            cached,
            meta={"course_id": resolved_course_id, "sub_id": resolved_sub_id},
            source="cache",
        )
        return

    timeline = await api.get_ppt_timeline(resolved_course_id, resolved_sub_id)
    cache.set(cache_key, timeline, "zhiyun_ppt")
    _emit_zhiyun_success(
        "ppt_timeline",
        timeline,
        meta={"course_id": resolved_course_id, "sub_id": resolved_sub_id},
    )


async def _cmd_transcript(sub_id: str, *, include_translation: bool = False, raw: bool = False):
    from zju_cache import CacheManager

    api = _get_api()
    cache = CacheManager()
    transcript = await _load_transcript_cached(api, cache, sub_id)
    segments = api._normalize_transcript_segments(transcript, include_translation=include_translation)
    payload = {
        "sub_id": str(sub_id),
        "segments": segments,
    }
    if raw:
        payload["raw"] = transcript
    _emit_zhiyun_success(
        "transcript_segments",
        payload,
        meta={"sub_id": str(sub_id), "include_translation": include_translation, "raw": raw},
        source="cache" if transcript is not None else "live",
    )


def main():
    import argparse
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    parser = argparse.ArgumentParser(description="智云课堂工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="搜索智云课程（旁路能力，当前平台下可能为空）")
    p_search.add_argument("--teacher", default="", help="教师姓名")
    p_search.add_argument("--keyword", default="", help="搜索关键词")

    p_mine = sub.add_parser("my-courses", help="列出当前账号的课程（默认推荐）")
    p_mine.add_argument("--teacher", default="", help="教师姓名")
    p_mine.add_argument("--keyword", default="", help="课程关键词")

    p_videos = sub.add_parser("videos", help="获取课程视频元数据")
    p_videos.add_argument("--course", default="", help="课程名称")
    p_videos.add_argument("--course-id", default="", help="课程 ID")
    p_videos.add_argument("--teacher", default="", help="教师姓名")
    p_videos.add_argument("--with-all-status", action="store_true", help="包含未转字幕视频")

    p_ppt = sub.add_parser("ppt", help="获取 PPT 时间轴")
    p_ppt.add_argument("--course", default="", help="课程名称")
    p_ppt.add_argument("--course-id", default="", help="课程 ID")
    p_ppt.add_argument("--sub-id", default="", help="视频/子课程 ID")
    p_ppt.add_argument("--teacher", default="", help="教师姓名")
    p_ppt.add_argument("--index", type=int, default=0, help="视频索引，0=最新")

    p_sub = sub.add_parser("subtitle", help="获取指定视频字幕（默认纯文本）")
    p_sub.add_argument("--sub-id", required=True, help="视频/子课程 ID")
    p_sub.add_argument("--timestamps", action="store_true", help="保留时间戳")
    p_sub.add_argument("--include-translation", action="store_true", help="附带翻译文本")
    p_sub.add_argument("--no-filter-fillers", action="store_true", help="不过滤口头语/低信息碎片")

    p_transcript = sub.add_parser("transcript", help="获取字幕原始分段")
    p_transcript.add_argument("--sub-id", required=True, help="视频/子课程 ID")
    p_transcript.add_argument("--include-translation", action="store_true", help="附带翻译文本")
    p_transcript.add_argument("--raw", action="store_true", help="附带原始接口返回 JSON")

    p_lec = sub.add_parser("lecture", help="从当前账号课程中获取讲座纯文本")
    p_lec.add_argument("--course", required=True, help="课程名称")
    p_lec.add_argument("--teacher", default="", help="教师姓名（可选）")
    p_lec.add_argument("--index", type=int, default=0, help="讲座索引，0=最新（默认 0）")
    p_lec.add_argument("--timestamps", action="store_true", help="保留时间戳")
    p_lec.add_argument("--include-translation", action="store_true", help="附带翻译文本")
    p_lec.add_argument("--no-filter-fillers", action="store_true", help="不过滤口头语/低信息碎片")

    args = parser.parse_args()

    try:
        if args.command == "search":
            if not args.teacher and not args.keyword:
                from zju_output import emit_error

                emit_error(message="请至少提供 --teacher 或 --keyword", platform="zhiyun", feature="search")
            asyncio.run(_cmd_search(args.teacher, args.keyword))
        elif args.command == "my-courses":
            asyncio.run(_cmd_my_courses(args.teacher, args.keyword))
        elif args.command == "videos":
            asyncio.run(
                _cmd_videos(
                    args.course,
                    args.teacher,
                    args.course_id,
                    args.with_all_status,
                )
            )
        elif args.command == "ppt":
            asyncio.run(
                _cmd_ppt(
                    course_name=args.course,
                    teacher_name=args.teacher,
                    course_id=args.course_id,
                    sub_id=args.sub_id,
                    lecture_index=args.index,
                )
            )
        elif args.command == "subtitle":
            asyncio.run(
                _cmd_subtitle(
                    args.sub_id,
                    timestamps=args.timestamps,
                    include_translation=args.include_translation,
                    filter_fillers=not args.no_filter_fillers,
                )
            )
        elif args.command == "transcript":
            asyncio.run(
                _cmd_transcript(
                    args.sub_id,
                    include_translation=args.include_translation,
                    raw=args.raw,
                )
            )
        elif args.command == "lecture":
            asyncio.run(
                _cmd_lecture(
                    args.course,
                    args.teacher,
                    args.index,
                    timestamps=args.timestamps,
                    include_translation=args.include_translation,
                    filter_fillers=not args.no_filter_fillers,
                )
            )
    except Exception as e:
        from zju_output import emit_error

        emit_error(message=str(e) or e.__class__.__name__, platform="zhiyun", feature=args.command)


if __name__ == "__main__":
    main()
