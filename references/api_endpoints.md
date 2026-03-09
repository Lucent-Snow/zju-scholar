# ZJU API Endpoints Reference

## 统一认证 (zjuam.zju.edu.cn)

### GET /cas/login
获取登录页面和 execution token。
- Response: HTML, 提取 `name="execution" value="..."`
- Cookies: 返回初始 session cookies

### GET /cas/v2/getPubKey
获取 RSA 公钥。
- Response: JSON `{"modulus":"...", "exponent":"..."}`

### POST /cas/login
提交登录。
- Content-Type: `application/x-www-form-urlencoded`
- Body: `username={学号}&password={RSA加密后密码}&execution={token}&_eventId=submit&rememberMe=true`
- Success: Set-Cookie `iPlanetDirectoryPro`
- Failure: 无 `iPlanetDirectoryPro` cookie

### GET /cas/login?service={service_url}
CAS 服务登录，用于跳转到各服务。
- Cookies: `iPlanetDirectoryPro`
- Response: 302 redirect with service ticket

### OAuth 2.0 (智云课堂)
- Authorize URL: `GET /cas/oauth2.0/authorize?client_id=ObXIv4FvjcC1e9hVcS&redirect_uri=...&response_type=code`
- Callback: `GET /cas/oauth2.0/callbackAuthorize?client_id=...&ticket=ST-xxx`
- 通过 tgmedia.cmc.zju.edu.cn 中转，最终在 `get-info?code=xxx` 响应的 `_token` cookie 中获取 JWT

---

## 教务网 ZDBK (zdbk.zju.edu.cn)

### 登录
- Service URL: `https://zdbk.zju.edu.cn/jwglxt/xtgl/login_ssologin.html`
- 登录后获取: `JSESSIONID` (path=/jwglxt) + `route` cookies

### POST /jwglxt/kbcx/xskbcx_cxXsKb.html
获取课表。
- Cookies: `JSESSIONID`, `route`
- Content-Type: `application/x-www-form-urlencoded`
- Body: `xnm={year}&xqm={semester_code}`
  - semester_code: `3`=秋冬, `12`=春夏, `16`=短学期
- Response: HTML/JSON, 提取 `(?<="kbList":)\[(.*?)\](?=,"xh")`
- Session fields: `sfqd`, `xqj`, `dsz`, `kcb` (含 `<br>` 分隔), `xxq`, `djj`, `skcd`

### POST /jwglxt/cxdy/xscjcx_cxXscjIndex.html?doType=query&queryModel.showCount=5000
获取所有成绩。
- Cookies: `JSESSIONID`, `route`
- Response: 提取 `(?<="items":)\[(.*?)\](?=,"limit")`
- Grade fields: `xkkh`, `kcmc`, `xf`, `cj`, `jd`

### POST /jwglxt/zycjtj/xszgkc_cxXsZgkcIndex.html?doType=query&queryModel.showCount=5000
获取主修成绩。
- 同上，额外标记 `major=true`

### POST /jwglxt/xskscx/kscx_cxXsgrksIndex.html?doType=query&queryModel.showCount=5000
获取考试安排。
- Cookies: `JSESSIONID`, `route`
- Response: 提取 `(?<="items":)\[(.*?)\](?=,"limit")`
- Exam fields:
  - 期中: `qzkssj`, `qzjsmc`, `qzzwxh`
  - 期末: `kssj`, `jsmc`, `zwxh`
  - 时间格式: `2021年01月22日(08:00-10:00)` 或 `第N天(HH:MM-HH:MM)`

---

## 学在浙大 Courses (courses.zju.edu.cn)

### 登录
- 入口: `GET https://courses.zju.edu.cn/user/index` + iPlanetDirectoryPro cookie
- 循环跟随重定向，最终获取 `session` cookie
- 最终重定向: `Location: https://courses.zju.edu.cn/user/index`

### GET /api/todos
获取作业/DDL 列表。
- Cookies: `session`
- Response: JSON `{"todo_list": [{id, title, course_name, course_code, type, end_time, ...}]}`

---

## 智云课堂

### 登录流程 (OAuth 2.0)
1. `GET tgmedia.cmc.zju.edu.cn/index.php?r=auth/login&tenant_code=112&forward=classroom.zju.edu.cn`
2. → 302 到 `zjuam.zju.edu.cn/cas/oauth2.0/authorize?client_id=ObXIv4FvjcC1e9hVcS`
3. → 302 链 (callbackAuthorize) → `tgmedia.cmc.zju.edu.cn/...get-info?code=ST-xxx`
4. → JWT 在 `_token` / `JWTUser` cookie 中

### GET classroom.zju.edu.cn/pptnote/v1/searchlist
搜索课程。
- Headers: `Authorization: Bearer {JWT}`
- Params: `tenant_id=112`, `page`, `per_page=16`, `realname={教师名}`, `tenant_code=112`, `user_id`, `user_name={学号}`
- Response: `{"data": {"list": [{course_id, title, term_name, lecturer_name, realname, kkxy_name}]}}`

### GET yjapi.cmc.zju.edu.cn/courseapi/v3/multi-search/get-course-detail
获取课程详情和视频列表。
- Headers: `Authorization: Bearer {JWT}`, `Referer: https://classroom.zju.edu.cn/coursedetail?course_id={id}&tenant_code=112`
- Params: `course_id`, `student={学号}`
- Response: `{"code": 0, "data": {"sub_list": {...}, "teachers": [...]}}`
- 视频字段: `id` (sub_id), `sub_title`, `sub_status` (`"6"` = 有字幕), `lecturer_name`

### GET yjapi.cmc.zju.edu.cn/courseapi/v3/web-socket/search-trans-result
获取字幕。
- Headers: `Authorization: Bearer {JWT}`, `Referer: https://classroom.zju.edu.cn/livingroom?sub_id={id}`
- Params: `sub_id`, `format=json`
- Response: `{"list": [{start_time, text}]}` 或 `{"data": {"list": [...]}}`

---

## 成绩转换映射

### 五分制 → 四分制 (4.3 满分)
| 五分制 | 四分制 |
|--------|--------|
| 5.0    | 4.3    |
| 4.8    | 4.2    |
| 4.5    | 4.1    |
| 4.2    | 4.0    |
| ≤4.0   | 原值   |

### 等级制 → 百分制
| 等级 | 百分制 |
|------|--------|
| A+   | 95     |
| A    | 90     |
| A-   | 87     |
| B+   | 83     |
| B    | 80     |
| B-   | 77     |
| C+   | 73     |
| C    | 70     |
| C-   | 67     |
| D    | 60     |
| F    | 0      |
| 优秀 | 90     |
| 良好 | 80     |
| 中等 | 70     |
| 及格 | 60     |
| 合格 | 75     |

### GPA 排除规则
- 不计学分: 弃修、待录、缓考、无效
- 不计 GPA: 合格、不合格、体育课(xtwkc)
