"""zju_auth.py — 浙大统一认证 + 各服务登录

翻译自 Celechron Dart 代码:
- lib/http/zjuServices/zjuam.dart  — RSA + CAS 登录
- lib/http/zjuServices/zdbk.dart   — ZDBK 教务网登录
- lib/http/zjuServices/courses.dart — 学在浙大登录
"""

import re
import ssl
import httpx


def _ssl_context_allow_legacy_dh() -> ssl.SSLContext:
    """返回允许较小 DH 密钥的 SSL 上下文，用于连接仍使用弱 DH 的浙大服务器（学在浙大、智云等）。"""
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return ctx


class ZjuAuth:
    def __init__(self, timeout: float = 8.0, webvpn=None):
        """
        Args:
            timeout: HTTP 请求超时
            webvpn: 可选的 WebVpnSession 实例。传入后所有请求走 WebVPN 代理。
        """
        self.timeout = timeout
        self._webvpn = webvpn
        self._iplanet: str | None = None
        self._zdbk_cookies: dict | None = None
        self._courses_session: str | None = None
        self._zhiyun_jwt: str | None = None

    def _url(self, url: str) -> str:
        """如果启用了 WebVPN，转换 URL。"""
        if self._webvpn and self._webvpn.logged_in:
            from zju_webvpn import convert_url
            return convert_url(url)
        return url

    def _make_client(self, **kwargs) -> httpx.AsyncClient:
        """创建 HTTP 客户端，WebVPN 模式下自动注入 cookie。直连时使用允许弱 DH 的 SSL 上下文以兼容学在浙大、智云等服务器。"""
        kwargs.setdefault("follow_redirects", False)
        kwargs.setdefault("timeout", self.timeout)
        if self._webvpn and self._webvpn.logged_in:
            kwargs.setdefault("verify", True)
            return self._webvpn.make_client(**kwargs)
        kwargs.setdefault("verify", _ssl_context_allow_legacy_dh())
        return httpx.AsyncClient(**kwargs)

    def _convert_redirect(self, location: str) -> str:
        """处理重定向 URL: WebVPN 模式下转换非 WebVPN 的 URL。"""
        if not location:
            return location
        if location.startswith("http://"):
            location = location.replace("http://", "https://", 1)
        if self._webvpn and self._webvpn.logged_in:
            from zju_webvpn import WEBVPN_HOST, convert_url
            if WEBVPN_HOST not in location:
                return convert_url(location)
        return location

    @property
    def is_logged_in(self) -> bool:
        return self._iplanet is not None

    @property
    def iplanet(self) -> str | None:
        return self._iplanet

    @property
    def zdbk_cookies(self) -> dict | None:
        return self._zdbk_cookies

    @property
    def courses_session(self) -> str | None:
        return self._courses_session

    @property
    def zhiyun_jwt(self) -> str | None:
        return self._zhiyun_jwt

    async def sso_login(self, username: str, password: str) -> str:
        """统一认证登录，返回 iPlanetDirectoryPro cookie 值。

        流程: GET login page → GET RSA pubkey → encrypt password → POST login
        """
        async with self._make_client() as client:
            # Step 1: GET login page to get execution token and cookies
            resp = await client.get(self._url("https://zjuam.zju.edu.cn/cas/login"))
            cookies = dict(resp.cookies)
            body = resp.text

            match = re.search(r'name="execution" value="(.*?)"', body)
            if not match:
                raise RuntimeError("无法获取 execution token")
            execution = match.group(1)

            # Step 2: GET RSA public key
            resp = await client.get(
                self._url("https://zjuam.zju.edu.cn/cas/v2/getPubKey"),
                cookies=cookies,
            )
            cookies.update(dict(resp.cookies))
            key_body = resp.text

            mod_match = re.search(r'"modulus":"(.*?)"', key_body)
            exp_match = re.search(r'"exponent":"(.*?)"', key_body)
            if not mod_match or not exp_match:
                raise RuntimeError("无法获取 RSA 公钥")

            modulus_hex = mod_match.group(1)
            exponent_hex = exp_match.group(1)

            # Step 3: RSA encrypt password (same as zjuam.dart:48-54)
            mod_int = int(modulus_hex, 16)
            exp_int = int(exponent_hex, 16)
            pwd_hex = password.encode("utf-8").hex()
            pwd_int = int(pwd_hex, 16)
            encrypted_int = pow(pwd_int, exp_int, mod_int)
            pwd_enc = format(encrypted_int, "x").zfill(128)

            # Step 4: POST login
            resp = await client.post(
                self._url("https://zjuam.zju.edu.cn/cas/login"),
                data={
                    "username": username,
                    "password": pwd_enc,
                    "execution": execution,
                    "_eventId": "submit",
                    "rememberMe": "true",
                },
                cookies=cookies,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            # Extract iPlanetDirectoryPro from response cookies
            iplanet = resp.cookies.get("iPlanetDirectoryPro")
            if not iplanet:
                raise RuntimeError("学号或密码错误")

            self._iplanet = iplanet
            return iplanet

    async def login_zdbk(self, iplanet: str | None = None) -> dict:
        """教务网 ZDBK 登录，返回 cookies dict {JSESSIONID, route}。

        流程: CAS service login → follow redirect → extract cookies
        """
        iplanet = iplanet or self._iplanet
        if not iplanet:
            raise RuntimeError("iPlanetDirectoryPro 无效，请先登录")

        async with self._make_client() as client:
            # Step 1: CAS service login for ZDBK
            resp = await client.get(
                self._url(
                    "https://zjuam.zju.edu.cn/cas/login"
                    "?service=https%3A%2F%2Fzdbk.zju.edu.cn%2Fjwglxt%2Fxtgl%2Flogin_ssologin.html"
                ),
                cookies={"iPlanetDirectoryPro": iplanet},
            )

            location = resp.headers.get("location")
            if not location:
                raise RuntimeError("iPlanetDirectoryPro 无效")
            location = self._convert_redirect(location)

            # Step 2: Follow redirect to ZDBK
            resp = await client.get(location)

            # Parse Set-Cookie headers manually to handle multiple same-name cookies
            jsessionid = None
            route = None
            for header_val in resp.headers.multi_items():
                if header_val[0].lower() == "set-cookie":
                    cookie_str = header_val[1]
                    if cookie_str.startswith("JSESSIONID="):
                        # Take the one with path=/jwglxt if multiple exist
                        if "/jwglxt" in cookie_str or jsessionid is None:
                            jsessionid = cookie_str.split("=", 1)[1].split(";")[0]
                    elif cookie_str.startswith("route="):
                        route = cookie_str.split("=", 1)[1].split(";")[0]

            if not jsessionid:
                raise RuntimeError("无法获取 JSESSIONID")
            if not route:
                raise RuntimeError("无法获取 route")

            self._zdbk_cookies = {"JSESSIONID": jsessionid, "route": route}
            return self._zdbk_cookies

    async def login_courses(self, iplanet: str | None = None) -> str:
        """学在浙大 Courses 登录，返回 session cookie 值。

        流程: GET /user/index → follow redirects manually → extract session cookie
        """
        iplanet = iplanet or self._iplanet
        if not iplanet:
            raise RuntimeError("iPlanetDirectoryPro 无效，请先登录")

        cookies = {"iPlanetDirectoryPro": iplanet}
        session_value = None

        async with self._make_client() as client:
            url = self._url("https://courses.zju.edu.cn/user/index")
            max_redirects = 20
            for _ in range(max_redirects):
                resp = await client.get(url, cookies=cookies)
                # Collect cookies from each response
                cookies.update(dict(resp.cookies))

                if "session" in resp.cookies:
                    session_value = resp.cookies["session"]

                if resp.is_redirect:
                    next_url = resp.headers.get("location", "")
                    next_url = self._convert_redirect(next_url)
                    if next_url.rstrip("/").endswith("courses.zju.edu.cn/user/index") or \
                       ("courses.zju.edu.cn" in next_url and next_url.endswith("/user/index")):
                        # Final redirect — session should be set
                        if session_value:
                            break
                    url = next_url
                else:
                    break

        if not session_value:
            raise RuntimeError("无法获取 session cookie")

        self._courses_session = session_value
        return session_value

    async def login_zhiyun(self, iplanet: str | None = None) -> str:
        """智云课堂登录，返回 JWT Bearer token。

        完整 OAuth 2.0 流程:
        1. tgmedia.cmc.zju.edu.cn/index.php?r=auth/login → 302 到 OAuth authorize
        2. zjuam OAuth authorize + iPlanetDirectoryPro → 302 链 → tgmedia/get-info?code=xxx
        3. tgmedia/get-info 返回 JWT
        """
        if self._webvpn and self._webvpn.logged_in:
            jwt = await self._login_zhiyun_via_webvpn()
            self._zhiyun_jwt = jwt
            return jwt

        iplanet = iplanet or self._iplanet
        if not iplanet:
            raise RuntimeError("iPlanetDirectoryPro 无效，请先登录")

        cookies = {"iPlanetDirectoryPro": iplanet}
        jwt = None

        async with self._make_client() as client:
            # Step 1: Hit tgmedia auth/login to get OAuth authorize URL
            resp = await client.get(
                self._url(
                    "https://tgmedia.cmc.zju.edu.cn/index.php"
                    "?r=auth/login&auType=&tenant_code=112"
                    "&forward=https%3A%2F%2Fclassroom.zju.edu.cn%2F"
                ),
            )
            # Collect tgmedia cookies (PHPSESSID, _csrf, etc.)
            tgmedia_cookies = dict(resp.cookies)

            if not resp.is_redirect:
                raise RuntimeError("智云认证失败：tgmedia 未重定向")

            oauth_url = resp.headers.get("location", "")
            oauth_url = self._convert_redirect(oauth_url)
            if "oauth2.0/authorize" not in oauth_url and "oauth2" not in oauth_url:
                raise RuntimeError(f"智云认证失败：非预期的重定向 {oauth_url[:100]}")

            # Step 2: Hit OAuth authorize with iPlanetDirectoryPro
            url = oauth_url
            max_redirects = 10
            for _ in range(max_redirects):
                resp = await client.get(url, cookies=cookies)
                cookies.update(dict(resp.cookies))

                if not resp.is_redirect:
                    break

                url = resp.headers.get("location", "")
                url = self._convert_redirect(url)

                # When we reach tgmedia/get-info with code, that's our target
                if "tgmedia.cmc.zju.edu.cn" in url and "code=" in url:
                    # Step 3: Hit tgmedia/get-info with the OAuth code + tgmedia cookies
                    all_cookies = {**tgmedia_cookies, **cookies}
                    # 确保 URL 也经过转换
                    target_url = self._url(url) if "webvpn" not in url else url
                    resp = await client.get(target_url, cookies=all_cookies)

                    # Follow any further redirects from tgmedia
                    final_cookies = dict(resp.cookies)
                    body = resp.text

                    # Try extracting JWT from response
                    jwt = self._extract_jwt(resp, body, final_cookies)

                    # If tgmedia redirects further, follow
                    if not jwt and resp.is_redirect:
                        next_url = resp.headers.get("location", "")
                        next_url = self._convert_redirect(next_url)
                        if next_url:
                            all_cookies.update(final_cookies)
                            resp2 = await client.get(next_url, cookies=all_cookies)
                            jwt = self._extract_jwt(resp2, resp2.text, dict(resp2.cookies))

                    break

            if not jwt:
                raise RuntimeError(
                    "无法自动获取智云 JWT。请手动登录 classroom.zju.edu.cn 后，"
                    "从浏览器开发者工具中复制 Authorization header 的 Bearer token，"
                    "并通过 --zhiyun-token 参数提供。"
                )

            self._zhiyun_jwt = jwt
            return jwt

    async def _login_zhiyun_via_webvpn(self) -> str:
        """WebVPN 模式下登录智云课堂并通过 cookie 桥提取 JWT。"""
        auth_url = (
            "https://tgmedia.cmc.zju.edu.cn/index.php"
            "?r=auth/login&auType=&tenant_code=112"
            "&forward=https%3A%2F%2Fclassroom.zju.edu.cn%2F"
        )

        # 先访问课堂首页，再触发 tgmedia 登录链。
        async with self._webvpn.make_client(
            timeout=self.timeout,
            verify=True,
            follow_redirects=True,
        ) as client:
            await client.get(self._url("https://classroom.zju.edu.cn/"))
            await client.get(self._url(auth_url))

        candidates = [
            ("classroom.zju.edu.cn", "/"),
            ("tgmedia.cmc.zju.edu.cn", "/"),
        ]
        for host, path in candidates:
            cookies = await self._webvpn.get_app_cookies(host=host, path=path)
            jwt = self._extract_jwt(None, "", cookies)
            if jwt:
                return jwt

        raise RuntimeError(
            "WebVPN 已登录，但未能从 cookie 桥中提取智云 JWT。"
        )

    @staticmethod
    def _extract_jwt(resp, body: str, cookies: dict) -> str | None:
        """从响应中提取 JWT token。"""
        import urllib.parse

        def _unwrap_jwt(raw: str) -> str | None:
            """从原始值中提取真正的 JWT（eyJ... 格式）。
            
            tgmedia 返回的 _identity cookie 是 PHP 序列化格式，
            真正的 JWT 嵌套在里面，需要 URL 解码后用正则提取。
            """
            decoded = urllib.parse.unquote(raw)
            jwt_match = re.search(
                r'(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)',
                decoded,
            )
            if jwt_match:
                return jwt_match.group(1)
            # 如果本身就是 JWT 格式，直接返回
            if raw.startswith("eyJ") and raw.count(".") == 2:
                return raw
            return None

        # Strategy 1: Check cookies
        for name in ["_token", "JWTUser", "token", "jwt", "access_token", "Authorization", "_identity"]:
            val = cookies.get(name)
            if val and len(val) > 20:
                extracted = _unwrap_jwt(val)
                if extracted:
                    return extracted

        # Strategy 2: Check JSON response
        if resp is not None:
            try:
                data = resp.json()
                token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("data", {}).get("token")
                    or data.get("data", {}).get("access_token")
                )
                if token:
                    extracted = _unwrap_jwt(token)
                    return extracted or token
            except Exception:
                pass

        # Strategy 3: Check HTML/JS for embedded token
        token_match = re.search(
            r'(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)',
            body,
        )
        if token_match:
            return token_match.group(1)

        return None

    def set_zhiyun_jwt(self, jwt: str):
        """手动设置智云 JWT（当自动获取失败时使用）。"""
        self._zhiyun_jwt = jwt

    def logout(self):
        """清除所有认证状态。"""
        self._iplanet = None
        self._zdbk_cookies = None
        self._courses_session = None
        self._zhiyun_jwt = None
