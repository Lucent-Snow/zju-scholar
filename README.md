# ZJU Scholar — 浙大学习助手 (Claude Code Skill)

浙大统一认证登录 + 教务数据查询 + 学在浙大课程/资源 + 智云课堂内容获取，作为 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) Skill 使用。

## 功能

- **统一认证登录** — 一次登录，自动获取教务网、学在浙大、智云课堂的 session
- **统一会话管理** — 所有平台脚本共享同一份本地 session / WebVPN 状态
- **统一 JSON 输出** — 数据脚本统一输出 `ok/platform/feature/meta/data` 结构
- **统一入口，按平台/功能分层** — skill 本身是统一入口，内部按“教务 / 学在浙大 / 智云课堂”与“课程 / 资源 / 字幕 / PPT”等能力拆分
- **课表查询** — 按学年学期获取课程安排
- **成绩 & GPA** — 获取所有成绩，自动计算四种制式的 GPA（五分制 / 4.3满分四分制 / 4.0满分四分制 / 百分制）
- **考试安排** — 获取期中期末考试时间、地点、座位号
- **作业 DDL** — 从学在浙大获取待办作业列表
- **学在浙大课程** — 课程列表、课程详情、模块、活动、课件、课堂互动详情
- **学在浙大资源** — 云盘资源列表、下载、上传
- **智云课堂** — 默认从“我的课程/最近学习”定位课程，并支持视频元数据、PPT 时间轴、字幕原文与纯文本讲座提取

## 安装

### 1. 安装依赖

```bash
pip install httpx>=0.27.0
```

需要 Python 3.10+。

### 2. 安装 Skill

将本项目复制到 Claude Code 的 skills 目录：

```bash
# macOS / Linux
cp -r . ~/.claude/skills/zju-scholar

# Windows (PowerShell)
Copy-Item -Recurse . "$env:USERPROFILE\.claude\skills\zju-scholar"
```

或者创建符号链接：

```bash
# macOS / Linux
ln -s "$(pwd)" ~/.claude/skills/zju-scholar

# Windows (管理员 PowerShell)
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\zju-scholar" -Target "$(Get-Location)"
```

### 3. 首次登录

在 Claude Code 中说「帮我登录浙大」，或手动运行：

```bash
python ~/.claude/skills/zju-scholar/scripts/zju_login.py -u 你的学号 -p 你的密码
```

登录成功后会自动保存 session，后续查询无需重复登录（session 过期后需要重新登录）。

## 使用

安装后在 Claude Code 中直接对话即可：

| 你说 | Claude 会做 |
|------|-------------|
| 我这学期有什么课？ | 查询当前学期课表 |
| 我的 GPA 怎么样？ | 获取成绩并计算 GPA |
| 下周有什么考试？ | 查询考试安排 |
| 最近有什么 DDL？ | 获取作业截止日期 |
| 帮我列一下学在浙大的课程资料 | 查询课程资料 / 课程活动 |
| 下载我云盘里最新的 PDF | 查询资源并下载 |
| 帮我找张三老师的课 | 尝试智云旁路搜索课程 |
| 上周的数据科学讲了什么？ | 从我的课程中获取智云课堂纯文本字幕 |
| 给我这个智云课程的视频信息和 PPT | 输出视频元数据和 PPT 时间轴 |

## 项目结构

```
zju-scholar/
├── SKILL.md                   # Skill 定义（Claude Code 读取）
├── scripts/
│   ├── zju_login.py           # 登录脚本
│   ├── zju_academic.py        # 教务数据查询（课表/成绩/考试/作业）
│   ├── zju_courses.py         # 学在浙大（课程/活动/课件/资源）
│   ├── zju_zhiyun.py          # 智云课堂（搜索/视频/PPT/字幕）
│   ├── zju_auth.py            # 统一认证模块
│   ├── zju_api.py             # ZDBK + Courses API
│   ├── zju_cache.py           # 本地缓存管理
│   ├── zju_output.py          # 统一 JSON 输出
│   ├── zju_session.py         # 统一会话恢复
│   └── requirements.txt       # Python 依赖
├── references/
│   └── api_endpoints.md       # API 端点参考文档
├── data/                      # [运行时生成] 凭证和 session
│   ├── credentials.json
│   └── session.json
└── cache/                     # [运行时生成] 查询缓存
```

## 能力分层

### 1. 教务网 / Academic

- `zju_academic.py`
- 功能：课表、成绩、GPA、考试、DDL

### 2. 学在浙大 / Courses

- `zju_courses.py`
- 功能：课程列表、课程详情、课程活动、课件、课堂互动、个人资源列表、资源下载上传

### 3. 智云课堂 / Zhiyun

- `zju_zhiyun.py`
- 功能：我的课程、课程视频元数据、PPT 时间轴、字幕原文、纯文本讲座提取

### 4. 公共层 / Shared

- `zju_session.py`：统一恢复本地 session / WebVPN
- `zju_output.py`：统一 JSON 输出
- `zju_api.py`：底层 API 封装
- `zju_cache.py`：统一缓存

## 脚本说明

### zju_login.py — 登录

```bash
python scripts/zju_login.py -u 学号 -p 密码   # 首次登录
python scripts/zju_login.py                    # 使用已保存凭证重新登录
python scripts/zju_login.py --status           # 查看登录状态
python scripts/zju_login.py --zhiyun-token TOKEN  # 手动设置智云 JWT
```

登录流程：浙大统一认证 (SSO) → 教务网 (ZDBK) → 学在浙大 (Courses) → 智云课堂 (OAuth 2.0)

### zju_academic.py — 教务数据

```bash
python scripts/zju_academic.py courses --year 2025 --semester 2   # 2025-2026 春夏课表
python scripts/zju_academic.py grades                              # 成绩和 GPA
python scripts/zju_academic.py exams                               # 考试安排
python scripts/zju_academic.py todos                               # 作业 DDL
```

学期编码：`1` = 秋冬，`2` = 春夏，`3` = 短学期

### zju_courses.py — 学在浙大

```bash
python scripts/zju_courses.py course-list --page-size 20
python scripts/zju_courses.py course-list --status ongoing --page-size 20
python scripts/zju_courses.py course-list --status finished --page-size 20
python scripts/zju_courses.py course-detail --course-id 94434
python scripts/zju_courses.py activities --course-id 94434
python scripts/zju_courses.py activity --activity-id 123456
python scripts/zju_courses.py classrooms --course-id 94434
python scripts/zju_courses.py classroom --classroom-id 654321
python scripts/zju_courses.py coursewares --course-id 94434
python scripts/zju_courses.py resources --type document --page-size 10
python scripts/zju_courses.py resource-download --resource-id 19533038 --output-dir downloads
python scripts/zju_courses.py resource-upload --file ./notes.pdf
```

课程状态参数：

- `--status ongoing`：进行中的课程
- `--status notStarted`：尚未开始的课程
- `--status finished`：已结束课程

说明：

- `course-list` 现已按前端真实行为改为 `POST /api/my-courses`
- `--status finished` 不依赖后端单次状态过滤；脚本会先读取 `my-semesters`，再按学期聚合课程并在本地过滤 `ended/finished/completed/closed`
- `coursewares` 从课程接口返回的 `activities[].uploads[]` 展平，不再错误读取空的顶层 `coursewares/uploads`

### zju_zhiyun.py — 智云课堂

```bash
python scripts/zju_zhiyun.py my-courses --keyword 数据科学   # 默认推荐：从我的课程定位
python scripts/zju_zhiyun.py videos --course-id 82136       # 视频元数据
python scripts/zju_zhiyun.py ppt --course-id 82136 --sub-id 1895913
python scripts/zju_zhiyun.py transcript --sub-id 1895913
python scripts/zju_zhiyun.py lecture --course 数据科学       # 默认输出过滤口头语后的纯文本讲座内容
python scripts/zju_zhiyun.py subtitle --sub-id 12345         # 默认输出过滤口头语后的纯文本字幕
python scripts/zju_zhiyun.py subtitle --sub-id 12345 --timestamps
python scripts/zju_zhiyun.py subtitle --sub-id 12345 --no-filter-fillers
python scripts/zju_zhiyun.py search --teacher 张三           # 可选：全站搜索
python scripts/zju_zhiyun.py search --teacher 张智君 --keyword 生理心理学
```

## 缓存策略

| 数据 | 缓存时长 |
|------|----------|
| 课表 | 7 天 |
| 成绩 | 6 小时 |
| 考试 | 12 小时 |
| 作业 | 1 小时 |
| 学在浙大课程列表 | 1 小时 |
| 学在浙大课程详情 | 6 小时 |
| 学在浙大活动/课堂互动/课件 | 30 分钟 |
| 学在浙大资源列表 | 15 分钟 |
| 智云搜索 | 4 小时 |
| 我的课程 | 1 小时 |
| 智云视频元数据 | 1 小时 |
| 智云 PPT | 永久 |
| 智云字幕 | 永久 |

缓存存储在 `cache/` 目录，可手动删除以强制刷新。

## 输出结构

所有数据脚本统一输出 JSON：

```json
{
  "ok": true,
  "platform": "courses",
  "feature": "course_list",
  "source": "live",
  "generated_at": "2026-03-10T06:49:10+00:00",
  "meta": {},
  "data": {}
}
```

字段含义：

- `platform`：`academic` / `courses` / `zhiyun`
- `feature`：具体功能名，例如 `course_list`、`coursewares`、`ppt`、`transcript`
- `source`：`live` 或 `cache`
- `meta`：请求参数
- `data`：标准化后的业务数据

## 注意事项

- Session 会过期（通常几小时），过期后重新运行 `zju_login.py` 即可
- 智云 JWT 在校外会通过 WebVPN + cookie 桥自动获取；极少情况下可能失败，此时再手动设置
- `my-courses` / `lecture` 是智云默认推荐流程；`search` 仅作为旁路能力
- `search` 会自动补齐 `user_id/user_name`，并在关键词无结果时尝试更短的模糊片段；如果已知老师，优先同时传 `--teacher`
- 智云字幕脚本默认输出适合阅读和 AI 消化的纯文本，会过滤口头语/低信息碎片；如需更接近原始分段可加 `--no-filter-fillers`
- 学在浙大历史课程的状态字段并不总能被后端可靠过滤；已结束课程查询以“按学期聚合 + 本地状态过滤”为准
- 凭证明文存储在本地 `data/credentials.json`，请注意安全
- **智云课堂 API（classroom.zju.edu.cn）需要校内网络或 WebVPN**；当前脚本已支持通过 WebVPN 访问并自动补齐 JWT

## 致谢

认证和 API 逻辑翻译自 [Celechron](https://github.com/Celechron/Celechron) Flutter 项目的 Dart 代码。

## License

GNU GPL v3.0
