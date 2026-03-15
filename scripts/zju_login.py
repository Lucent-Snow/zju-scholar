"""zju_login.py — 登录脚本

用法:
  python zju_login.py                  # 使用已保存的凭证登录
  python zju_login.py -u 学号 -p 密码  # 指定凭证登录（同时保存）
  python zju_login.py --webvpn         # 通过 WebVPN 登录（校外网络）
  python zju_login.py --save-only -u 学号 -p 密码  # 只保存凭证不登录
  python zju_login.py --status         # 查看当前登录状态
  python zju_login.py --zhiyun-token TOKEN  # 设置智云 JWT

登录后将 session 信息保存到 skill 文件夹的 data/ 目录。
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
CRED_FILE = DATA_DIR / "credentials.json"
SESSION_FILE = DATA_DIR / "session.json"

# 确保 scripts 目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from zju_auth import ZjuAuth
from zju_console import ensure_utf8_io


JWT_RE = re.compile(r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


def normalize_zhiyun_token(raw: str) -> str:
    """接受裸 JWT、_token cookie 值或整段 cookie 文本，统一提取出 JWT。"""
    if not raw:
        return ""

    value = raw.strip()
    if value.startswith("Bearer "):
        value = value[7:].strip()

    match = JWT_RE.search(value)
    if match:
        return match.group(1)

    return value


def load_credentials() -> dict:
    if CRED_FILE.exists():
        try:
            return json.loads(CRED_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_credentials(username: str, password: str, zhiyun_token: str = ""):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {"username": username, "password": password}
    zhiyun_token = normalize_zhiyun_token(zhiyun_token)
    if zhiyun_token:
        data["zhiyun_token"] = zhiyun_token
    else:
        old = load_credentials()
        if old.get("zhiyun_token"):
            data["zhiyun_token"] = old["zhiyun_token"]
    CRED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_session(session: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session() -> dict:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


async def do_login(username: str, password: str, zhiyun_token: str = "", use_webvpn: bool = False):
    zhiyun_token = normalize_zhiyun_token(zhiyun_token)
    # 检测网络环境
    from zju_webvpn import WebVpnSession
    probe = WebVpnSession()
    is_campus = await probe.check_campus_network()

    if use_webvpn or not is_campus:
        if not is_campus and not use_webvpn:
            print("检测到非校园网环境，自动启用 WebVPN...")
        await _do_login_webvpn(username, password, zhiyun_token, probe)
    else:
        await _do_login_direct(username, password, zhiyun_token)


async def _do_login_webvpn(username: str, password: str, zhiyun_token: str, vpn):
    """通过 WebVPN 登录所有服务。"""
    print("正在登录 WebVPN...")
    ok = await vpn.login(username, password)
    if not ok:
        raise RuntimeError("WebVPN 登录失败，请检查学号密码")
    print("  WebVPN 登录成功")

    print(f"正在通过 WebVPN 登录统一认证 (学号: {username})...")
    await vpn.sso_login_via_vpn(username, password)
    print("  统一认证登录成功")

    session = {"username": username, "webvpn_enabled": True, "webvpn_cookies": vpn.cookies}

    print("正在通过 WebVPN 登录教务网(ZDBK)...")
    await vpn.login_service_via_vpn(
        "https://zjuam.zju.edu.cn/cas/login"
        "?service=https%3A%2F%2Fzdbk.zju.edu.cn%2Fjwglxt%2Fxtgl%2Flogin_ssologin.html"
    )
    session["webvpn_cookies"] = vpn.cookies
    print("  教务网登录成功")

    print("正在通过 WebVPN 登录学在浙大(Courses)...")
    await vpn.login_service_via_vpn(
        "https://zjuam.zju.edu.cn/cas/login"
        "?service=https%3A%2F%2Fcourses.zju.edu.cn%2Fuser%2Findex"
    )
    session["webvpn_cookies"] = vpn.cookies
    print("  学在浙大登录成功")

    if zhiyun_token:
        session["zhiyun_jwt"] = zhiyun_token
        print("  智云 JWT 已设置（手动提供）")
    else:
        print("正在通过 WebVPN 登录智云课堂...")
        try:
            auth = ZjuAuth(webvpn=vpn)
            jwt = await auth.login_zhiyun()
            session["zhiyun_jwt"] = jwt
            print("  智云课堂登录成功")
        except RuntimeError as e:
            print(f"  智云课堂自动登录失败: {e}")
            print("  可通过 --zhiyun-token 参数手动设置")

    save_session(session)
    print("\n登录完成，session 已保存（WebVPN 模式）。")
    return session


async def _do_login_direct(username: str, password: str, zhiyun_token: str):
    """直连模式登录（校园网内）。"""
    auth = ZjuAuth()

    print(f"正在登录统一认证 (学号: {username})...")
    await auth.sso_login(username, password)
    print("  统一认证登录成功")

    session = {"username": username}

    print("正在登录教务网(ZDBK)...")
    zdbk_cookies = await auth.login_zdbk()
    session["zdbk_cookies"] = zdbk_cookies
    print("  教务网登录成功")

    print("正在登录学在浙大(Courses)...")
    courses_session = await auth.login_courses()
    session["courses_session"] = courses_session
    print("  学在浙大登录成功")

    if zhiyun_token:
        session["zhiyun_jwt"] = zhiyun_token
        print("  智云 JWT 已设置（手动提供）")
    else:
        print("正在登录智云课堂...")
        try:
            jwt = await auth.login_zhiyun()
            session["zhiyun_jwt"] = jwt
            print("  智云课堂登录成功")
        except RuntimeError as e:
            print(f"  智云课堂自动登录失败: {e}")
            print("  可通过 --zhiyun-token 参数手动设置")

    save_session(session)
    print("\n登录完成，session 已保存。")
    return session


def show_status():
    cred = load_credentials()
    session = load_session()

    print("=== 凭证 ===")
    if cred.get("username"):
        print(f"  学号: {cred['username']}")
        print(f"  密码: {'*' * len(cred.get('password', ''))}")
        print(f"  智云 JWT: {'已设置' if cred.get('zhiyun_token') else '未设置'}")
    else:
        print("  未保存凭证")

    print("\n=== Session ===")
    if session:
        print(f"  学号: {session.get('username', '未知')}")
        if session.get("webvpn_enabled"):
            print(f"  模式: WebVPN (校外)")
        else:
            print(f"  模式: 直连 (校内)")
            print(f"  ZDBK: {'已登录' if session.get('zdbk_cookies') else '未登录'}")
            print(f"  Courses: {'已登录' if session.get('courses_session') else '未登录'}")
        print(f"  智云 JWT: {'已设置' if session.get('zhiyun_jwt') else '未设置'}")
    else:
        print("  未登录")


def main():
    ensure_utf8_io()
    parser = argparse.ArgumentParser(description="浙大统一认证登录")
    parser.add_argument("-u", "--username", help="学号")
    parser.add_argument("-p", "--password", help="密码")
    parser.add_argument("--zhiyun-token", help="智云课堂 JWT，支持裸 JWT、_token cookie 值或整段 cookie 文本")
    parser.add_argument("--save-only", action="store_true", help="只保存凭证不登录")
    parser.add_argument("--webvpn", action="store_true", help="强制通过 WebVPN 登录（校外网络）")
    parser.add_argument("--status", action="store_true", help="查看当前状态")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    # 获取凭证：优先命令行参数，其次已保存的凭证
    username = args.username
    password = args.password
    zhiyun_token = normalize_zhiyun_token(args.zhiyun_token or "")

    if not username or not password:
        cred = load_credentials()
        username = username or cred.get("username", "")
        password = password or cred.get("password", "")
        zhiyun_token = zhiyun_token or normalize_zhiyun_token(cred.get("zhiyun_token", ""))

    if not username or not password:
        print("错误: 请提供学号和密码。用法: python zju_login.py -u 学号 -p 密码")
        sys.exit(1)

    # 保存凭证
    save_credentials(username, password, zhiyun_token)

    if args.save_only:
        print("凭证已保存。")
        return

    # 如果只提供了 zhiyun-token，更新 session 中的 JWT
    if args.zhiyun_token and not args.username and not args.password:
        session = load_session()
        session["zhiyun_jwt"] = normalize_zhiyun_token(args.zhiyun_token)
        save_session(session)
        # 也更新凭证文件
        cred = load_credentials()
        cred["zhiyun_token"] = normalize_zhiyun_token(args.zhiyun_token)
        CRED_FILE.write_text(json.dumps(cred, ensure_ascii=False, indent=2), encoding="utf-8")
        print("智云 JWT 已更新。")
        return

    try:
        asyncio.run(do_login(username, password, zhiyun_token, use_webvpn=args.webvpn))
    except Exception as e:
        print(f"登录失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
