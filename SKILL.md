---
name: zju-scholar
description: >
  浙大学习助手。当用户需要查询课表、成绩、GPA、考试安排、作业DDL，
  或获取智云课堂课程内容、课程字幕时使用。触发关键词：课表、成绩、GPA、
  考试、作业、DDL、智云、字幕、学习内容、我的课程。
---

# ZJU Scholar — 浙大学习助手

通过 Python 脚本调用浙大教务网(ZDBK)、学在浙大(Courses)和智云课堂的数据。

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

## 脚本 3: zju_zhiyun.py — 智云课堂

```bash
# 默认推荐：列出当前账号课程
python <SKILL>/scripts/zju_zhiyun.py my-courses --keyword 数据科学

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
- "帮我找张三老师的课" → `zju_zhiyun.py search --teacher 张三`（旁路能力，可能为空）
- "帮我看看上周的数据科学讲了什么" → `zju_zhiyun.py lecture --course 数据科学`

## 数据存储

所有数据都存储在 skill 文件夹内:
- `data/credentials.json` — 学号、密码
- `data/session.json` — 登录后的 session 信息
- `cache/` — 缓存目录（课表、成绩等查询结果）

## 注意事项

- Session 会过期，如果查询报错请重新运行 `zju_login.py`
- 校外网络自动通过 WebVPN 代理，无需额外配置
- WebVPN 的 ticket cookie 也会过期，过期后重新登录即可
- 智云默认推荐走“我的课程/最近学习”链路，不依赖全站搜索
- `search` 仅作为旁路能力，但现在会自动补齐 `user_id/user_name`，并在关键词无结果时尝试更短的模糊片段
- 若已知教师名，优先同时传 `--teacher`，结果会明显更准
- 智云字幕默认输出过滤口头语后的纯文本，适合直接阅读或交给 AI；如需更接近原始分段可显式加 `--no-filter-fillers`
- 校外网络会通过 WebVPN 自动补齐智云 JWT，无需浏览器
- 依赖: `httpx`, `pycryptodome` (见 scripts/requirements.txt)
