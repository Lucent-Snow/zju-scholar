---
name: zju-scholar
description: >
  浙大学习助手。当用户需要查询课表、成绩、GPA、考试安排、作业DDL、
  学在浙大课程/资源、智云课堂课程内容、PPT、视频元数据、课程字幕、
  CC98 热门帖、帖子搜索、帖子内容时使用。
  这是统一功能入口，但内部按平台和功能分层：教务网、学在浙大、智云课堂、
  CC98 论坛，以及统一会话与统一 JSON 输出层。
  触发关键词：课表、成绩、GPA、考试、作业、DDL、学在浙大、课程资料、资源、
  智云、字幕、PPT、学习内容、我的课程、CC98、论坛、热门帖子、帖子搜索。
---

# ZJU Scholar — 浙大学习助手

通过 Python 脚本调用浙大教务网(ZDBK)、学在浙大(Courses)、智云课堂和 CC98 论坛的数据。
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

教务网(ZDBK)数据：课表、成绩、考试。

```bash
# 获取当前学期课表（自动推算，推荐）
python <SKILL>/scripts/zju_academic.py courses

# 获取指定学期课表
python <SKILL>/scripts/zju_academic.py courses --year 2024 --semester 1

# 获取所有成绩和 GPA
python <SKILL>/scripts/zju_academic.py grades

# 仅当前学期成绩
python <SKILL>/scripts/zju_academic.py grades --current

# 指定学期成绩
python <SKILL>/scripts/zju_academic.py grades --year 2025 --semester 1

# 获取当前学期考试安排（默认）
python <SKILL>/scripts/zju_academic.py exams

# 获取所有考试安排
python <SKILL>/scripts/zju_academic.py exams --all
```

学期自动推算规则（UTC+8）：
- 9-12月 → 当年秋冬（year=当年, semester=1）
- 1月 → 上年秋冬（year=去年, semester=1）
- 2-6月 → 上年春夏（year=去年, semester=2）
- 7-8月 → 上年短学期（year=去年, semester=3）

不传 --year/--semester 时自动使用当前学期，推荐这种用法。

## 脚本 3: zju_courses.py — 学在浙大

学在浙大平台数据：课程管理、作业DDL、课件资料、云盘资源。

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

## 脚本 5: zju_cc98.py — CC98 论坛

使用原则：
- CC98 仅用于补充热门帖、按需搜索、查看单帖详情，不用于大规模归档或批量爬取
- 优先小范围请求，`search/posts` 默认控制在必要范围内，避免高频翻页
- 搜索接口有限流；连续搜索至少间隔 1 秒，不要并发刷接口
- 如果用户提出“全站抓取”“批量扫版面”“长期同步全论坛”等需求，应明确拒绝并改为按需查询

```bash
# 登录 CC98（搜索能力需要）
python <SKILL>/scripts/zju_cc98.py login --username 用户名 --password 密码

# 热门帖子
python <SKILL>/scripts/zju_cc98.py hot --period weekly
python <SKILL>/scripts/zju_cc98.py hot --period monthly
python <SKILL>/scripts/zju_cc98.py hot --period history

# 搜索帖子
python <SKILL>/scripts/zju_cc98.py search --keyword 常微分 --size 5
python <SKILL>/scripts/zju_cc98.py search --keyword 常微分 --board-id 68 --size 5

# 帖子详情 / 楼层 / 热门回帖
python <SKILL>/scripts/zju_cc98.py topic --topic-id 6454407
python <SKILL>/scripts/zju_cc98.py posts --topic-id 6454407 --from 0 --size 10
python <SKILL>/scripts/zju_cc98.py hot-posts --topic-id 6454407

# 可选：通过现有 ZJU WebVPN 会话访问
python <SKILL>/scripts/zju_cc98.py hot --period weekly --webvpn
```

## 学期编码

| 参数 | 含义 |
|------|------|
| --year 2024 --semester 1 | 2024-2025 秋冬学期 |
| --year 2024 --semester 2 | 2024-2025 春夏学期 |
| --year 2024 --semester 3 | 2024-2025 短学期 |

## 典型对话 → 脚本调用

- "我这学期有什么课？" → `zju_academic.py courses`（自动推算当前学期）
- "我的 GPA 怎么样？" → `zju_academic.py grades`
- "这学期成绩怎么样？" → `zju_academic.py grades --current`
- "下周有什么考试？" → `zju_academic.py exams`（默认当前学期）
- "最近有什么 DDL？" → `zju_courses.py todos`
- "帮我看这门课的活动和资料" → `zju_courses.py activities --course-id ...` / `zju_courses.py coursewares --course-id ...`
- "把我云盘里最新的 PDF 列出来" → `zju_courses.py resources --type document`
- "帮我找张三老师的课" → `zju_zhiyun.py search --teacher 张三`（旁路能力，可能为空）
- "帮我看看上周的数据科学讲了什么" → `zju_zhiyun.py lecture --course 数据科学`
- "给我这个智云课程的视频和 PPT" → `zju_zhiyun.py videos ...` / `zju_zhiyun.py ppt ...`

## 分层约定

- 教务层（课表/成绩/考试）：`zju_academic.py`
- 学在浙大课程层（课程管理/作业DDL/课件/云盘）：`zju_courses.py`
- 智云课堂层（视频/字幕/PPT）：`zju_zhiyun.py`
- CC98 论坛层（热门帖/搜索/帖子详情）：`zju_cc98.py`
- 公共层：`zju_session.py`、`zju_output.py`、`zju_api.py`、`zju_cache.py`

职责边界：作业/DDL 归学在浙大（`zju_courses.py todos`），教务层只管课表、成绩、考试。

如果用户说“统一入口”，优先理解为这个 skill 统一承接能力，而不是合并成一个脚本。
新增能力时保持按平台、按功能分类。

## 数据存储

所有数据都存储在 skill 文件夹内:
- `data/credentials.json` — 学号、密码
- `data/session.json` — 登录后的 session 信息
- `data/cc98_credentials.json` — CC98 用户名、密码
- `data/cc98_session.json` — CC98 access_token / refresh_token
- `data/profile.json` — 用户学业档案（年级、当前学期、校区等）
- `cache/` — 缓存目录（课表、成绩等查询结果）
- `output/` — 大文本输出目录（字幕、讲座文本等）

### profile.json — 用户学业档案

存储用户当前的学业状态，所有脚本共享。格式：

```json
{
  "grade": "大二下",
  "year": "2025",
  "semester": "2",
  "label": "2025-2026 春夏",
  "campus": "紫金港"
}
```

- `year` + `semester` 是课表/成绩/考试的默认学期参数
- 不传 --year/--semester 时自动读取 profile，profile 也没有则按日期推算
- 每学期开学时需要更新（手动编辑或通过脚本）

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
- 字幕/讲座文本超过 800 字时自动存到 `output/` 目录，JSON 只返回文件路径、字数和前 300 字预览；AI 需要全文时用 read 工具读取文件
- 短文本（≤800字）仍直接在 JSON 的 `text` 字段返回
- 校外网络会通过 WebVPN 自动补齐智云 JWT，无需浏览器
- CC98 热门帖和公开帖子可匿名访问，但搜索需要论坛登录态
- CC98 服务器容量有限，不要进行大规模爬取、批量翻页抓取或高频轮询；只做当前任务所需的最小查询
- CC98 搜索接口有限流，1 秒内重复搜索可能返回 `last_search_in_1_seconds`
- CC98 支持通过现有 `zju_login.py --webvpn` 建立的 ZJU WebVPN 会话访问
- 学在浙大历史课程查询不要假设后端状态过滤可靠；已结束课程以脚本内学期聚合结果为准
- 依赖: `httpx`, `pycryptodome` (见 scripts/requirements.txt)
