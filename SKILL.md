---
name: zju-scholar
description: >
  浙大学习助手。当用户需要查询课表、成绩、GPA、考试安排、作业DDL、
  学在浙大课程/资源、智云课堂课程内容、PPT、视频元数据、课程字幕时使用。
  这是统一功能入口，但内部按平台和功能分层：教务网、学在浙大、智云课堂、
  以及统一会话与统一 JSON 输出层。
  触发关键词：课表、成绩、GPA、考试、作业、DDL、学在浙大、课程资料、资源、
  智云、字幕、PPT、学习内容、我的课程。
---

# ZJU Scholar — 浙大学习助手

通过 Python 脚本调用浙大教务网(ZDBK)、学在浙大(Courses)和智云课堂的数据。
所有数据脚本统一输出 JSON，且共享同一份本地 session / WebVPN 状态。

这是一个统一入口 skill，不是单脚本工具。内部按平台和功能拆分，避免把不同来源、
不同稳定性的接口揉在一起。

脚本位于本 Skill 目录下的 `scripts/` 子目录。

默认安装路径:
- macOS / Linux: `~/.claude/skills/zju-scholar`
- Windows: `%USERPROFILE%\.claude\skills\zju-scholar`

以下示例中 `<SKILL>` 代表实际安装路径，请替换为上述路径。

## 首次使用 — 登录

需要先登录才能查询数据。凭证保存在 skill 文件夹的 `data/` 目录中。

在校外网络环境下，脚本会自动检测并通过 WebVPN 代理访问校内服务。

```bash
# 首次登录（保存凭证 + 登录所有服务，自动检测网络环境）
python <SKILL>/scripts/zju_login.py -u 学号 -p 密码

# 强制使用 WebVPN（校外网络）
python <SKILL>/scripts/zju_login.py --webvpn

# 后续登录（使用已保存的凭证）
python <SKILL>/scripts/zju_login.py

# 查看状态
python <SKILL>/scripts/zju_login.py --status

# 设置智云 JWT（自动获取失败时手动设置）
python <SKILL>/scripts/zju_login.py --zhiyun-token TOKEN
```

## 脚本 1: zju_login.py — 登录

登录浙大统一认证，同时登录教务网、学在浙大、智云课堂，将 session 保存到本地。

## 脚本 2: zju_academic.py — 教务数据查询

```bash
# 获取课表
python <SKILL>/scripts/zju_academic.py courses --year 2024 --semester 1

# 获取成绩和 GPA
python <SKILL>/scripts/zju_academic.py grades

# 获取考试安排
python <SKILL>/scripts/zju_academic.py exams

# 获取作业/DDL
python <SKILL>/scripts/zju_academic.py todos
```

## 脚本 3: zju_courses.py — 学在浙大

```bash
# 当前课程列表
python <SKILL>/scripts/zju_courses.py course-list --page-size 20
python <SKILL>/scripts/zju_courses.py course-list --status ongoing --page-size 20
python <SKILL>/scripts/zju_courses.py course-list --status finished --page-size 20

# 课程详情 / 模块 / 活动 / 课堂互动 / 课件
python <SKILL>/scripts/zju_courses.py course-detail --course-id 94434
python <SKILL>/scripts/zju_courses.py modules --course-id 94434
python <SKILL>/scripts/zju_courses.py activities --course-id 94434
python <SKILL>/scripts/zju_courses.py classrooms --course-id 94434
python <SKILL>/scripts/zju_courses.py coursewares --course-id 94434

# 作业或活动详情
python <SKILL>/scripts/zju_courses.py activity --activity-id 123456

# 课堂互动详情
python <SKILL>/scripts/zju_courses.py classroom --classroom-id 654321

# 云盘资源
python <SKILL>/scripts/zju_courses.py resources --type document --page-size 10
python <SKILL>/scripts/zju_courses.py resource-download --resource-id 19533038 --output-dir downloads
python <SKILL>/scripts/zju_courses.py resource-upload --file ./notes.pdf
```

状态语义：

- `ongoing`：进行中的课程
- `notStarted`：尚未开始的课程
- `finished`：已结束课程

实现说明：

- 课程列表走前端真实使用的 `POST /api/my-courses`
- `finished` 会先读 `my-semesters`，再按学期聚合课程并本地过滤 `ended/finished/completed/closed`
- 课件列表从 `activities[].uploads[]` 展平，而不是读取不存在的顶层文件列表

## 脚本 4: zju_zhiyun.py — 智云课堂

```bash
# 默认推荐：列出当前账号课程
python <SKILL>/scripts/zju_zhiyun.py my-courses --keyword 数据科学

# 视频元数据 / PPT 时间轴 / 字幕原文
python <SKILL>/scripts/zju_zhiyun.py videos --course 数据科学
python <SKILL>/scripts/zju_zhiyun.py ppt --course 数据科学
python <SKILL>/scripts/zju_zhiyun.py transcript --sub-id 12345

# 一键获取讲座纯文本（默认过滤口头语，不带时间戳、不带翻译）
python <SKILL>/scripts/zju_zhiyun.py lecture --course 数据科学
python <SKILL>/scripts/zju_zhiyun.py lecture --course 数据科学 --timestamps
python <SKILL>/scripts/zju_zhiyun.py lecture --course 数据科学 --no-filter-fillers

# 获取指定视频字幕（默认过滤口头语后的纯文本）
python <SKILL>/scripts/zju_zhiyun.py subtitle --sub-id 12345
python <SKILL>/scripts/zju_zhiyun.py subtitle --sub-id 12345 --timestamps
python <SKILL>/scripts/zju_zhiyun.py subtitle --sub-id 12345 --no-filter-fillers

# 可选：全站搜索课程（当前平台下可能为空）
python <SKILL>/scripts/zju_zhiyun.py search --teacher 张三
python <SKILL>/scripts/zju_zhiyun.py search --keyword 数据科学
python <SKILL>/scripts/zju_zhiyun.py search --teacher 张智君 --keyword 生理心理学
```

## 学期编码

| 参数 | 含义 |
|------|------|
| --year 2024 --semester 1 | 2024-2025 秋冬学期 |
| --year 2024 --semester 2 | 2024-2025 春夏学期 |
| --year 2024 --semester 3 | 2024-2025 短学期 |

## 典型对话 → 脚本调用

- "我这学期有什么课？" → `zju_academic.py courses --year 2025 --semester 2`
- "我的 GPA 怎么样？" → `zju_academic.py grades`
- "下周有什么考试？" → `zju_academic.py exams`
- "最近有什么 DDL？" → `zju_academic.py todos`
- "帮我看这门课的活动和资料" → `zju_courses.py activities --course-id ...` / `zju_courses.py coursewares --course-id ...`
- "把我云盘里最新的 PDF 列出来" → `zju_courses.py resources --type document`
- "帮我找张三老师的课" → `zju_zhiyun.py search --teacher 张三`（旁路能力，可能为空）
- "帮我看看上周的数据科学讲了什么" → `zju_zhiyun.py lecture --course 数据科学`
- "给我这个智云课程的视频和 PPT" → `zju_zhiyun.py videos ...` / `zju_zhiyun.py ppt ...`

## 分层约定

- 教务层：`zju_academic.py`
- 学在浙大课程层：`zju_courses.py`
- 智云课堂层：`zju_zhiyun.py`
- 公共层：`zju_session.py`、`zju_output.py`、`zju_api.py`、`zju_cache.py`

如果用户说“统一入口”，优先理解为这个 skill 统一承接能力，而不是合并成一个脚本。
新增能力时保持按平台、按功能分类。

## 数据存储

所有数据都存储在 skill 文件夹内:
- `data/credentials.json` — 学号、密码
- `data/session.json` — 登录后的 session 信息
- `cache/` — 缓存目录（课表、成绩等查询结果）

## 注意事项

- Session 会过期，如果查询报错请重新运行 `zju_login.py`
- 校外网络自动通过 WebVPN 代理，无需额外配置
- WebVPN 的 ticket cookie 也会过期，过期后重新登录即可
- `zju_academic.py` / `zju_courses.py` / `zju_zhiyun.py` 都输出统一 JSON，可直接供 AI 继续处理
- 统一 JSON 结构为 `ok/platform/feature/source/generated_at/meta/data`
- 智云默认推荐走“我的课程/最近学习”链路，不依赖全站搜索
- `search` 仅作为旁路能力，但现在会自动补齐 `user_id/user_name`，并在关键词无结果时尝试更短的模糊片段
- 若已知教师名，优先同时传 `--teacher`，结果会明显更准
- 智云字幕默认输出过滤口头语后的纯文本，适合直接阅读或交给 AI；如需更接近原始分段可显式加 `--no-filter-fillers`
- 校外网络会通过 WebVPN 自动补齐智云 JWT，无需浏览器
- 学在浙大历史课程查询不要假设后端状态过滤可靠；已结束课程以脚本内学期聚合结果为准
- 依赖: `httpx`, `pycryptodome` (见 scripts/requirements.txt)
