"""zju_library.py — 浙大图书馆查询脚本

用法:
  python zju_library.py books                      # 查询在借图书
  python zju_library.py renew --barcode <barcode>  # 续借指定图书
  python zju_library.py renew --all                # 续借所有可续借图书
  python zju_library.py search <keyword>           # 搜索图书馆藏书
  python zju_library.py history [--size N]         # 查看借阅历史
  python zju_library.py hold --set-number <id> --set-entry <entry>  # 预约图书
  python zju_library.py seat [--date YYYY-MM-DD]   # 查看座位余量
  python zju_library.py status                     # 查看认证状态
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zju_output import emit_error, emit_success
from zju_session import load_session

ALEPH_API = "http://api.lib.zju.edu.cn/aleph"
MOBLIB_API = "http://api.lib.zju.edu.cn/moblib"
OPAC_BASE = "https://opac.zju.edu.cn"
BOOKING_BASE = "https://booking.lib.zju.edu.cn"
CAS_AUTH_URL = (
    "https://zjuam.zju.edu.cn/cas/oauth2.0/authorize"
    "?response_type=code"
    "&client_id=EcZUPTTg7zcD6FpFPn"
    "&redirect_uri=http://m.lib.zju.edu.cn/pages/wechat/auth"
)
LIBRARY_CODE = "ZJU50"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ───────────────────────────── helpers ─────────────────────────────

def _load_library_session() -> dict:
    p = DATA_DIR / "library_session.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_library_session(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / "library_session.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_date(s: str) -> datetime | None:
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _days_until(s: str) -> int | None:
    d = _parse_date(s)
    if d is None:
        return None
    return (d - datetime.now()).days


# ───────────────────────────── OAuth2 auth ──────────────────────────

async def _oauth2_authenticate(iplanet: str) -> dict:
    """CAS OAuth2 flow → returns {bor_id, token, name}."""
    # Manual redirect following: httpx doesn't forward cookies across redirects
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, verify=True) as client:
        # Step 1: GET authorize → 302 to CAS login
        resp = await client.get(
            CAS_AUTH_URL,
            cookies={"iPlanetDirectoryPro": iplanet},
        )
        location = resp.headers.get("location", "")
        if not location:
            raise RuntimeError("OAuth2 认证失败: authorize 未返回重定向")

        # Step 2: Follow to CAS login with iplanet → 302 to callback with ticket
        resp2 = await client.get(location, cookies={"iPlanetDirectoryPro": iplanet})
        location2 = resp2.headers.get("location", "")
        if not location2:
            raise RuntimeError("OAuth2 认证失败: CAS 登录未通过，请重新运行 zju_login.py")

        # Step 3: Follow callback → 302 to redirect_uri with code
        resp3 = await client.get(location2)
        location3 = resp3.headers.get("location", "")

        parsed = urlparse(location3)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        if not code:
            raise RuntimeError(
                "OAuth2 认证失败: 未收到授权码。请重新运行 zju_login.py 刷新 session。"
            )

        # Step 4: Exchange code for token
        resp4 = await client.post(
            f"{MOBLIB_API}/binduni",
            json={"code": code, "openid": ""},
        )
        resp4.raise_for_status()
        payload = resp4.json()

    if payload.get("statuscode") != 0:
        raise RuntimeError(f"binduni 失败: {payload.get('message', payload)}")

    d = payload["data"]
    result = {
        "bor_id": d["tlv_bor_id"],
        "token": d["token"],
        "name": d.get("name", ""),
        "school_code": d.get("tlv_school_code", ""),
    }
    _save_library_session(result)
    return result


async def _ensure_library_auth(iplanet: str) -> dict:
    """Load cached library session or re-authenticate."""
    cached = _load_library_session()
    if cached.get("token") and cached.get("bor_id"):
        return cached
    return await _oauth2_authenticate(iplanet)


# ───────────────────────────── Aleph API (books, renew) ─────────────

async def _aleph_request(path: str, token: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15, verify=True) as client:
        resp = await client.get(
            f"{ALEPH_API}{path}",
            params=params or {},
            headers={"Authorization": token},
        )
        resp.raise_for_status()
        return resp.json()


async def api_books(iplanet: str) -> dict:
    auth = await _ensure_library_auth(iplanet)
    data = await _aleph_request("/bor_info", auth["token"], {"bor_id": auth["bor_id"]})

    borrowed = []
    raw = data.get("loan", []) or data.get("loans", []) or []
    if not raw:
        for key in ["data", "result"]:
            inner = data.get(key)
            if isinstance(inner, dict):
                raw = inner.get("loan", []) or inner.get("loans", []) or []
                if raw:
                    break

    for item in raw:
        title = item.get("title", "") or item.get("z13_title", "")
        author = item.get("author", "") or item.get("z13_author", "")
        barcode = item.get("barcode", "") or item.get("item_barcode", "") or item.get("z30_barcode", "")
        due = item.get("due_date", "") or item.get("z36_due_date", "")
        loan_date = item.get("loan_date", "") or item.get("z36_loan_date", "")
        call_no = item.get("call_no", "") or item.get("z30_call_no", "")
        days = _days_until(due)
        borrowed.append({
            "title": title,
            "author": author,
            "barcode": barcode,
            "loan_date": loan_date,
            "due_date": due,
            "call_no": call_no,
            "days_remaining": days,
            "is_overdue": (days is not None and days < 0),
        })

    return {"bor_id": auth["bor_id"], "name": auth.get("name", ""), "total": len(borrowed), "books": borrowed}


async def api_renew(iplanet: str, barcode: str) -> dict:
    auth = await _ensure_library_auth(iplanet)
    data = await _aleph_request("/renew", auth["token"], {
        "CON_LNG": "chi",
        "bor-id": auth["bor_id"],
        "library": LIBRARY_CODE,
        "item_barcode": barcode,
    })
    reply = ""
    if isinstance(data, dict):
        inner = data.get("data", data).get("renew", data.get("data", data))
        if isinstance(inner, dict):
            reply = inner.get("reply", "") or inner.get("result", "")
        else:
            reply = data.get("reply", "") or data.get("result", "")
    ok = isinstance(reply, str) and reply.lower() in ["ok", "success"]
    return {"barcode": barcode, "success": ok, "message": reply or ("续借成功" if ok else "续借失败")}


# ───────────────────────────── OPAC (search, history, hold) ─────────

def _save_opac_cookies(cookies: dict):
    cached = _load_library_session()
    cached["opac_cookies"] = cookies
    _save_library_session(cached)


async def _opac_init_session(iplanet: str) -> tuple[httpx.AsyncClient, dict[str, str], str]:
    """Create OPAC session, return (client, cookies, html).

    OPAC root page is a JS redirect to /F?RN=<random>. We follow it
    with iPlanetDirectoryPro cookie for CAS SSO.
    """
    import random as _rnd
    rn = _rnd.randint(100000000, 999999999)
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"}

    client = httpx.AsyncClient(timeout=20, follow_redirects=True, verify=True, headers=ua)
    resp = await client.get(
        f"{OPAC_BASE}/F?RN={rn}",
        cookies={"iPlanetDirectoryPro": iplanet},
    )
    html = resp.text
    cookies = dict(resp.cookies)
    cookies["iPlanetDirectoryPro"] = iplanet

    if "action=" not in html and "func=find-b" not in html:
        await client.aclose()
        raise RuntimeError("OPAC 会话初始化失败，无法找到搜索表单")

    _save_opac_cookies(cookies)
    return client, cookies, html


async def api_search(iplanet: str, keyword: str, size: int = 10) -> dict:
    """Search OPAC catalog."""
    client, cookies, html = await _opac_init_session(iplanet)
    try:
        # Extract form action URL (contains session hash)
        action_match = re.search(r'action="([^"]*)"', html)
        if not action_match:
            raise RuntimeError("无法找到 OPAC 搜索表单")

        form_url = action_match.group(1)
        if not form_url.startswith("http"):
            form_url = f"https://opac.zju.edu.cn{form_url}"

        # Submit search
        resp = await client.get(
            form_url,
            params={
                "func": "find-b",
                "find_code": "WRD",
                "request": keyword,
                "local_base": "ZJU01",
            },
            cookies=cookies,
        )
        result_html = resp.text

        # Hit count — OPAC shows "共 N 条" or "共N条记录"
        hit_match = re.search(r'共\s*(\d+)\s*条', result_html)
        if not hit_match:
            hit_match = re.search(r'prnnavigate\s*\(\s*(\d+)', result_html)
        total = int(hit_match.group(1)) if hit_match else 0

        # Extract book entries from OPAC HTML
        # Each result has numbered links and title text
        books = []
        # Find all title-like links (func=full-set-set)
        title_links = re.findall(
            r'href="([^"]*func=full-set-set[^"]*)"[^>]*>([^<]+)</a>',
            result_html,
        )
        # Also find doc IDs for hold
        doc_ids = re.findall(r"SetMark\('(\w+)'\)", result_html)

        # Group: each result set has consecutive links
        set_number = ""
        seen = set()
        for href, text in title_links:
            text = text.strip()
            if not text or len(text) < 3:
                continue
            # Skip navigation/metadata links
            if text in ["详细书目信息", "馆藏", "预约", "电子资源"]:
                continue
            # Extract set_number from URL
            sn_match = re.search(r'set_number=(\d+)', href)
            se_match = re.search(r'set_entry=(\d+)', href)
            if sn_match:
                set_number = sn_match.group(1)
            entry_num = se_match.group(1) if se_match else ""

            # Deduplicate by (set_number, entry_num)
            key = (set_number, entry_num)
            if key in seen:
                continue
            seen.add(key)

            # Check if it looks like a book title (has Chinese chars)
            if re.search(r'[\u4e00-\u9fff]', text) and entry_num:
                books.append({
                    "title": text.replace("&nbsp;", " ").replace("&amp;", "&"),
                    "set_number": set_number,
                    "set_entry": entry_num,
                })

        # Enrich with author/info from surrounding HTML
        # Each entry's HTML block contains author, publisher info in spans
        info_blocks = re.findall(
            r'set_entry=\d+[^>]*>[^<]+</a>(.*?)(?=set_entry=|</table>)',
            result_html, re.DOTALL,
        )
        for i, block in enumerate(info_blocks[:len(books)]):
            # Extract plain text segments
            segments = re.findall(r'>([^<]+)<', block)
            info_parts = [s.strip() for s in segments if s.strip() and len(s.strip()) > 1]
            # Filter out generic labels
            info_parts = [p for p in info_parts if p not in ["详细书目信息", "馆藏", "预约", "电子资源"]]
            if info_parts:
                books[i]["info"] = " | ".join(info_parts[:3])

        return {
            "keyword": keyword,
            "total": total,
            "showing": len(books[:size]),
            "books": books[:size],
        }
    finally:
        await client.aclose()


async def api_history(iplanet: str, size: int = 20) -> dict:
    """Get borrowing history from OPAC."""
    client, cookies, html = await _opac_init_session(iplanet)
    try:
        # Find "我的图书馆" link
        my_lib_match = re.search(r'href="([^"]*func=bor-info[^"]*)"', html)
        if not my_lib_match:
            # Try broader pattern
            my_lib_match = re.search(r'href="([^"]*)"[^>]*>我的图书馆', html)
        if not my_lib_match:
            raise RuntimeError("无法找到'我的图书馆'链接")

        lib_url = my_lib_match.group(1)
        if not lib_url.startswith("http"):
            lib_url = f"https://opac.zju.edu.cn{lib_url}"

        resp = await client.get(lib_url, cookies=cookies)
        my_html = resp.text

        # Parse borrowing summary
        history_match = re.search(r'借阅历史列表.*?(\d+)', my_html)
        total = int(history_match.group(1)) if history_match else 0

        # Find history link
        history_link = re.search(r'href="([^"]*)"[^>]*>借阅历史', my_html)

        items = []
        if history_link:
            h_url = history_link.group(1)
            if not h_url.startswith("http"):
                h_url = f"https://opac.zju.edu.cn{h_url}"

            resp2 = await client.get(h_url, cookies=cookies)
            h_html = resp2.text

            # Parse history table rows
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', h_html, re.DOTALL)
            for row in rows:
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if len(cells) >= 4:
                    title = re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else ""
                    author = re.sub(r'<[^>]+>', '', cells[2]).strip() if len(cells) > 2 else ""
                    loan_date = re.sub(r'<[^>]+>', '', cells[-2]).strip() if len(cells) > 3 else ""
                    return_date = re.sub(r'<[^>]+>', '', cells[-1]).strip() if len(cells) > 3 else ""
                    if title and title not in ["书名", "题名", "著者"]:
                        items.append({
                            "title": title,
                            "author": author,
                            "loan_date": loan_date,
                            "return_date": return_date,
                        })
                        if len(items) >= size:
                            break

        return {"total": total, "showing": len(items), "history": items}
    finally:
        await client.aclose()


async def api_hold(iplanet: str, set_number: str, set_entry: str) -> dict:
    """Reserve a book via OPAC hold form."""
    client, cookies, html = await _opac_init_session(iplanet)
    try:
        # Extract form action URL (session-scoped)
        action_match = re.search(r'action="([^"]*)"', html)
        if not action_match:
            raise RuntimeError("无法找到 OPAC 表单")
        form_base = action_match.group(1)
        if not form_base.startswith("http"):
            form_base = f"https://opac.zju.edu.cn{form_base}"
        # The hold endpoint is in the same session path
        session_prefix = re.sub(r'-\d+$', '', form_base)

        hold_url = f"{session_prefix}-01170"
        resp = await client.post(
            hold_url,
            data={
                "func": "hold",
                "set_number": set_number,
                "set_entry": set_entry,
                "CON_LNG": "chi",
                "adm_library": "ZJU50",
            },
            cookies=cookies,
        )

        body = resp.text
        success = resp.status_code == 200 and "error" not in body.lower()[:500]
        # Check for success indicators
        if "预约成功" in body or "hold placed" in body.lower():
            success = True
        if "已预约" in body or "already on hold" in body.lower():
            return {"set_number": set_number, "set_entry": set_entry, "success": True, "message": "该书已有预约"}

        return {
            "set_number": set_number,
            "set_entry": set_entry,
            "success": success,
            "message": "预约请求已提交" if success else "预约失败，请在网页端操作",
        }
    finally:
        await client.aclose()


# ───────────────────────────── Booking API (seat) ───────────────────

BOOKING_CAS_LOGIN = "https://zjuam.zju.edu.cn/cas/login?service=https://booking.lib.zju.edu.cn/api/cas/cas"
BOOKING_CAS_USER = "https://booking.lib.zju.edu.cn/api/cas/user"


def _load_credentials() -> dict:
    p = DATA_DIR / "credentials.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


async def _booking_authenticate(username: str, password: str) -> str:
    """Full CAS login flow for booking.lib.zju.edu.cn → returns JWT."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, verify=True) as client:
        # Step 1: GET CAS login page → extract execution token
        resp = await client.get(BOOKING_CAS_LOGIN)
        exe_match = re.search(r'name="execution"\s+value="([^"]+)"', resp.text)
        if not exe_match:
            raise RuntimeError("无法获取 CAS execution token")
        execution = exe_match.group(1)

        # Step 2: GET RSA public key
        pub_resp = await client.get("https://zjuam.zju.edu.cn/cas/v2/getPubKey")
        pub = pub_resp.json()
        modulus_hex = pub["modulus"]
        exponent_hex = pub["exponent"]

        # Step 3: RSA-encrypt password (same algorithm as zju_auth.py)
        mod_int = int(modulus_hex, 16)
        exp_int = int(exponent_hex, 16)
        pwd_int = int(password.encode("utf-8").hex(), 16)
        encrypted_int = pow(pwd_int, exp_int, mod_int)
        enc_pwd = format(encrypted_int, "x").zfill(128)

        # Step 4: POST CAS login
        login_resp = await client.post(
            BOOKING_CAS_LOGIN,
            data={
                "username": username,
                "password": enc_pwd,
                "execution": execution,
                "_eventId": "submit",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        ticket_loc = login_resp.headers.get("location", "")
        if "ticket" not in ticket_loc:
            raise RuntimeError("CAS 登录失败，未获得 ticket")

        # Step 5: Follow redirects to get cas token from SPA URL
        r2 = await client.get(ticket_loc)
        r3 = await client.get(r2.headers.get("location", ""))
        cas_loc = r3.headers.get("location", "")
        cas_match = re.search(r"cas=([^&\s#]+)", cas_loc)
        if not cas_match:
            raise RuntimeError("无法从重定向中提取 cas token")
        cas_token = cas_match.group(1)

        # Step 6: POST /api/cas/user → JWT
        token_resp = await client.post(
            BOOKING_CAS_USER,
            json={"cas": cas_token},
            headers={"Content-Type": "application/json"},
        )
        data = token_resp.json()
        jwt = data.get("member", {}).get("token", "")
        if not jwt:
            raise RuntimeError(f"无法获取 booking JWT: {data.get('msg', '')}")

        # Cache JWT
        cached = _load_library_session()
        cached["booking_token"] = jwt
        _save_library_session(cached)
        return jwt


async def _ensure_booking_token(iplanet: str) -> str:
    """Get or refresh booking JWT."""
    cached = _load_library_session()
    token = cached.get("booking_token", "")
    if token:
        return token
    cred = _load_credentials()
    if not cred.get("username") or not cred.get("password"):
        raise RuntimeError("未保存凭证，请先运行 python scripts/zju_login.py -u 学号 -p 密码")
    return await _booking_authenticate(cred["username"], cred["password"])


async def api_seat_status(iplanet: str, date: str | None = None, *, credentials: dict | None = None) -> dict:
    """Get seat availability from booking system."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    token = await _ensure_booking_token(iplanet)
    headers = {"Authorization": f"bearer{token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=15, verify=True) as client:
        resp = await client.get(
            f"{BOOKING_BASE}/api/room/list",
            params={"date": date, "type": "1"},
            headers=headers,
        )
        data = resp.json()

    rooms = []
    for room in (data.get("data") or []):
        rooms.append({
            "id": room.get("id"),
            "name": room.get("name", ""),
            "total": room.get("totalSeats", 0),
            "available": room.get("availableSeats", 0),
        })

    return {
        "date": date,
        "rooms": rooms,
        "note": "系统 7:00 开放次日预约" if not rooms else "",
    }


# ───────────────────────────── Status ───────────────────────────────

async def cmd_status():
    """Show auth status for all services."""
    session = load_session()
    lib_session = _load_library_session()

    status = {
        "iplanet": bool(session.get("iplanet")),
        "library_token": bool(lib_session.get("token")),
        "library_bor_id": lib_session.get("bor_id", ""),
        "library_name": lib_session.get("name", ""),
        "opac_cookies": bool(lib_session.get("opac_cookies")),
        "booking_token": bool(lib_session.get("booking_token")),
    }
    emit_success(platform="library", feature="status", data=status)


# ───────────────────────────── CLI commands ──────────────────────────

async def cmd_books(*, use_webvpn: bool = False):
    session = load_session()
    iplanet = session.get("iplanet")
    if not iplanet:
        raise RuntimeError("未登录，请先运行 python scripts/zju_login.py")
    result = await api_books(iplanet)
    emit_success(platform="library", feature="books", data=result)


async def cmd_renew(barcode: str | None = None, *, renew_all: bool = False, use_webvpn: bool = False):
    session = load_session()
    iplanet = session.get("iplanet")
    if not iplanet:
        raise RuntimeError("未登录，请先运行 python scripts/zju_login.py")

    if renew_all:
        books_data = await api_books(iplanet)
        renewable = [b for b in books_data.get("books", []) if not b.get("is_overdue")]
        if not renewable:
            emit_success(platform="library", feature="renew", data={"message": "没有可续借的图书"})
            return
        results = []
        for b in renewable:
            bc = b.get("barcode", "")
            if bc:
                r = await api_renew(iplanet, bc)
                results.append(r)
        emit_success(platform="library", feature="renew", data={"results": results})
    elif barcode:
        result = await api_renew(iplanet, barcode)
        emit_success(platform="library", feature="renew", data=result)
    else:
        raise RuntimeError("请指定 --barcode 或 --all")


async def cmd_search(keyword: str, size: int = 10):
    session = load_session()
    iplanet = session.get("iplanet")
    if not iplanet:
        raise RuntimeError("未登录，请先运行 python scripts/zju_login.py")
    result = await api_search(iplanet, keyword, size)
    emit_success(platform="library", feature="search", data=result)


async def cmd_history(size: int = 20):
    session = load_session()
    iplanet = session.get("iplanet")
    if not iplanet:
        raise RuntimeError("未登录，请先运行 python scripts/zju_login.py")
    result = await api_history(iplanet, size)
    emit_success(platform="library", feature="history", data=result)


async def cmd_hold(set_number: str, set_entry: str):
    session = load_session()
    iplanet = session.get("iplanet")
    if not iplanet:
        raise RuntimeError("未登录，请先运行 python scripts/zju_login.py")
    result = await api_hold(iplanet, set_number, set_entry)
    emit_success(platform="library", feature="hold", data=result)


async def cmd_seat(date: str | None = None):
    session = load_session()
    iplanet = session.get("iplanet")
    if not iplanet:
        raise RuntimeError("未登录，请先运行 python scripts/zju_login.py")
    cred = _load_credentials()
    result = await api_seat_status(iplanet, date, credentials=cred)
    emit_success(platform="library", feature="seat", data=result)


# ───────────────────────────── CLI parser ────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="浙大图书馆工具")
    parser.set_defaults(webvpn=False)
    parser.add_argument("--webvpn", action="store_true", help="通过 WebVPN 访问")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("books", help="查询在借图书")

    p_renew = sub.add_parser("renew", help="续借图书")
    p_renew.add_argument("--barcode", help="要续借的图书条码")
    p_renew.add_argument("--all", dest="renew_all", action="store_true", help="续借所有可续借图书")

    p_search = sub.add_parser("search", help="搜索图书馆藏书")
    p_search.add_argument("keyword", help="搜索关键词")
    p_search.add_argument("--size", type=int, default=10, help="返回数量")

    p_history = sub.add_parser("history", help="查看借阅历史")
    p_history.add_argument("--size", type=int, default=20, help="返回数量")

    p_hold = sub.add_parser("hold", help="预约图书")
    p_hold.add_argument("--set-number", required=True, help="搜索结果中的 set_number")
    p_hold.add_argument("--set-entry", required=True, help="搜索结果中的 set_entry")

    p_seat = sub.add_parser("seat", help="查看座位余量")
    p_seat.add_argument("--date", help="日期 (YYYY-MM-DD)，默认今天")

    sub.add_parser("status", help="查看认证状态")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        use_webvpn = getattr(args, "webvpn", False)
        if args.command == "books":
            asyncio.run(cmd_books(use_webvpn=use_webvpn))
        elif args.command == "renew":
            asyncio.run(cmd_renew(
                barcode=args.barcode,
                renew_all=args.renew_all,
                use_webvpn=use_webvpn,
            ))
        elif args.command == "search":
            asyncio.run(cmd_search(args.keyword, size=args.size))
        elif args.command == "history":
            asyncio.run(cmd_history(size=args.size))
        elif args.command == "hold":
            asyncio.run(cmd_hold(args.set_number, args.set_entry))
        elif args.command == "seat":
            asyncio.run(cmd_seat(date=args.date))
        elif args.command == "status":
            asyncio.run(cmd_status())
    except RuntimeError as e:
        emit_error(message=str(e), platform="library", feature=args.command)
    except Exception as e:
        emit_error(message=str(e) or e.__class__.__name__, platform="library", feature=args.command)


if __name__ == "__main__":
    main()
