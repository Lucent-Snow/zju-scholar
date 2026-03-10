"""zju_webvpn.py — 浙大 WebVPN 代理层

提供:
- WebVPN URL 转换 (AES-128-CFB 加密主机名)
- WebVPN 登录 (获取 ticket cookie)
- 透明代理 HTTP 客户端

参考: https://github.com/Ginsenvey/ZJU-New-WebVPN.Csharp
"""

import re
from urllib.parse import urlparse, quote
from Crypto.Cipher import AES

WEBVPN_HOST = "webvpn.zju.edu.cn"
WEBVPN_BASE = f"https://{WEBVPN_HOST}"
LOGIN_PAGE = f"{WEBVPN_BASE}/login"
LOGIN_POST = f"{WEBVPN_BASE}/do-login"

# 两个不同的密钥
KEY_URL = b"wrdvpnisthebest!"  # URL 主机名加密
KEY_PWD = b"wrdvpnisawesome!"  # 登录密码加密


def _aes_cfb128_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CFB (128-bit feedback) 加密。"""
    cipher = AES.new(key, AES.MODE_CFB, iv, segment_size=128)
    return cipher.encrypt(plaintext)


def _encrypt_field(plaintext: str, key: bytes) -> str:
    """加密字段: hex(key_ascii) + hex(aes(plaintext))[:2*len(plaintext)]

    与 C# BuildPassword 逻辑一致。
    """
    key_hex = key.decode("ascii").encode("ascii").hex()
    ct = _aes_cfb128_encrypt(plaintext.encode("utf-8"), key, key)
    ct_hex = ct.hex()
    # 只取前 2*len(plaintext) 个 hex 字符 (= len(plaintext) 字节)
    return key_hex + ct_hex[: 2 * len(plaintext)]


def encrypt_host(host: str) -> str:
    """加密主机名，用于 URL 转换。"""
    return _encrypt_field(host, KEY_URL)


def encrypt_password(password: str) -> str:
    """加密密码，用于 WebVPN 登录。"""
    return _encrypt_field(password, KEY_PWD)


def convert_url(url: str) -> str:
    """将普通 URL 转换为 WebVPN 代理 URL。

    例: https://zdbk.zju.edu.cn/jwglxt/path?q=1
      → https://webvpn.zju.edu.cn/https/{encrypted_host}/jwglxt/path?q=1
    """
    parsed = urlparse(url)
    scheme = parsed.scheme
    host = parsed.hostname
    port = parsed.port

    # 判断是否为非标准端口
    is_special_port = port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    )
    prop = f"{scheme}-{port}" if is_special_port else scheme

    # 加密主机名
    encrypted = encrypt_host(host)

    # 路径 + 查询字符串
    path = parsed.path or "/"
    suffix = path
    if parsed.query:
        suffix += "?" + parsed.query
    if parsed.fragment:
        suffix += "#" + parsed.fragment

    return f"{WEBVPN_BASE}/{prop}/{encrypted}{suffix}"


def unconvert_url(vpn_url: str) -> str | None:
    """尝试从 WebVPN URL 还原原始 URL (尽力而为，用于调试)。"""
    parsed = urlparse(vpn_url)
    if WEBVPN_HOST not in parsed.hostname:
        return None

    parts = parsed.path.strip("/").split("/", 2)
    if len(parts) < 2:
        return None

    prop = parts[0]  # e.g. "https" or "https-8443"
    rest = "/" + parts[2] if len(parts) > 2 else "/"

    # 解析 scheme 和端口
    if "-" in prop:
        scheme, port_str = prop.rsplit("-", 1)
        port_suffix = f":{port_str}"
    else:
        scheme = prop
        port_suffix = ""

    # 无法解密主机名 (需要 AES 解密)，返回 None
    return None


# --- WebVPN 登录 ---

import httpx
from html.parser import HTMLParser


class _FormParser(HTMLParser):
    """从 WebVPN 登录页提取隐藏表单字段。"""

    def __init__(self):
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return
        d = dict(attrs)
        if d.get("type") == "hidden" and d.get("name"):
            self.fields[d["name"]] = d.get("value", "")


class WebVpnSession:
    """WebVPN 会话管理。

    登录后持有 ticket cookie，可用于代理所有内网请求。
    """

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.cookies: dict[str, str] = {}
        self.logged_in = False

    @property
    def ticket(self) -> str | None:
        return self.cookies.get("wengine_vpn_ticketwebvpn_zju_edu_cn")

    async def login(self, username: str, password: str) -> bool:
        """登录 WebVPN，获取 ticket cookie。"""
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout,
            verify=True,
        ) as client:
            # Step 1: GET 登录页，获取 CSRF 和 captcha_id
            resp = await client.get(LOGIN_PAGE)

            parser = _FormParser()
            parser.feed(resp.text)
            fields = parser.fields

            csrf = fields.get("_csrf", "")
            captcha_id = fields.get("captcha_id", "")
            auth_type = fields.get("auth_type", "")

            # Step 2: 加密密码
            enc_pwd = encrypt_password(password)

            # Step 3: POST 登录
            form = {
                "_csrf": csrf,
                "auth_type": auth_type,
                "sms_code": "",
                "captcha": "",
                "needCaptcha": "false",
                "captcha_id": captcha_id,
                "username": username,
                "password": enc_pwd,
            }

            resp = await client.post(
                LOGIN_POST,
                data=form,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": LOGIN_PAGE,
                },
            )

            # 收集所有 cookie (去重)
            for cookie in client.cookies.jar:
                self.cookies[cookie.name] = cookie.value

            # 检查登录结果
            try:
                result = resp.json()
                if result.get("success"):
                    self.logged_in = True
                    return True
            except Exception:
                pass

            # 有些情况下登录成功是通过 302 重定向体现的
            if self.ticket:
                self.logged_in = True
                return True

            return False

    async def check_campus_network(self) -> bool:
        """检测是否在校园网内。"""
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=True) as client:
                resp = await client.get("https://mirrors.zju.edu.cn/api/is_campus_network")
                text = resp.text.strip()
                return text in ("1", "2")
        except Exception:
            return False

    def make_client(self, **kwargs) -> httpx.AsyncClient:
        """创建一个带 WebVPN cookie 的 httpx 客户端。

        注意: 调用方需要自行用 convert_url() 转换 URL。
        WebVPN 模式下建议使用 follow_redirects=True。
        """
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", True)
        kwargs.setdefault("follow_redirects", True)

        client = httpx.AsyncClient(cookies=self.cookies, **kwargs)
        return client

    async def sso_login_via_vpn(self, username: str, password: str):
        """通过 WebVPN 完成 SSO 登录。

        WebVPN 代理会在内部管理 iPlanetDirectoryPro cookie，
        不需要显式提取。登录后 self.cookies 会包含所有必要的 WebVPN cookie。
        """
        import re

        async with self.make_client() as client:
            # GET CAS login page
            resp = await client.get(convert_url("https://zjuam.zju.edu.cn/cas/login"))
            match = re.search(r'name="execution" value="(.*?)"', resp.text)
            if not match:
                raise RuntimeError("无法获取 execution token")
            execution = match.group(1)

            # GET RSA pubkey
            resp = await client.get(convert_url("https://zjuam.zju.edu.cn/cas/v2/getPubKey"))
            mod_match = re.search(r'"modulus":"(.*?)"', resp.text)
            exp_match = re.search(r'"exponent":"(.*?)"', resp.text)
            if not mod_match or not exp_match:
                raise RuntimeError("无法获取 RSA 公钥")

            mod_int = int(mod_match.group(1), 16)
            exp_int = int(exp_match.group(1), 16)
            pwd_int = int(password.encode("utf-8").hex(), 16)
            pwd_enc = format(pow(pwd_int, exp_int, mod_int), "x").zfill(128)

            # POST login
            resp = await client.post(
                convert_url("https://zjuam.zju.edu.cn/cas/login"),
                data={
                    "username": username,
                    "password": pwd_enc,
                    "execution": execution,
                    "_eventId": "submit",
                    "rememberMe": "true",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            # 更新 cookies (去重，保留最新值)
            self._sync_cookies(client)

    async def login_service_via_vpn(self, service_url: str):
        """通过 WebVPN 完成某个服务的 CAS 登录。

        WebVPN 代理会在内部管理服务的 session cookie。
        """
        async with self.make_client() as client:
            await client.get(convert_url(service_url))
            self._sync_cookies(client)

    def _sync_cookies(self, client: httpx.AsyncClient):
        """从 client 同步 cookies 回 self.cookies，去重保留最新值。"""
        for cookie in client.cookies.jar:
            self.cookies[cookie.name] = cookie.value
