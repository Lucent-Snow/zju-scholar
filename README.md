# ZJU Scholar — 浙大学习助手 (Claude Code Skill)

浙大统一认证登录 + 教务数据查询 + 智云课堂字幕获取，作为 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) Skill 使用。

## 功能

- **统一认证登录** — 一次登录，自动获取教务网、学在浙大、智云课堂的 session
- **课表查询** — 按学年学期获取课程安排
- **成绩 & GPA** — 获取所有成绩，自动计算四种制式的 GPA（五分制 / 4.3满分四分制 / 4.0满分四分制 / 百分制）
- **考试安排** — 获取期中期末考试时间、地点、座位号
- **作业 DDL** — 从学在浙大获取待办作业列表
- **智云课堂** — 按教师/关键词搜索课程，获取课堂录播字幕

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
| 帮我找张三老师的课 | 在智云搜索课程 |
| 上周的数据科学讲了什么？ | 获取智云课堂字幕 |

## 项目结构

```
zju-scholar/
├── SKILL.md                   # Skill 定义（Claude Code 读取）
├── scripts/
│   ├── zju_login.py           # 登录脚本
│   ├── zju_academic.py        # 教务数据查询（课表/成绩/考试/作业）
│   ├── zju_zhiyun.py          # 智云课堂（搜索/字幕）
│   ├── zju_auth.py            # 统一认证模块
│   ├── zju_api.py             # ZDBK + Courses API
│   ├── zju_cache.py           # 本地缓存管理
│   └── requirements.txt       # Python 依赖
├── references/
│   └── api_endpoints.md       # API 端点参考文档
├── data/                      # [运行时生成] 凭证和 session
│   ├── credentials.json
│   └── session.json
└── cache/                     # [运行时生成] 查询缓存
```

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

### zju_zhiyun.py — 智云课堂

```bash
python scripts/zju_zhiyun.py search --teacher 张三         # 按教师搜索
python scripts/zju_zhiyun.py search --keyword 数据科学     # 按关键词搜索
python scripts/zju_zhiyun.py subtitle --sub-id 12345       # 获取指定字幕
python scripts/zju_zhiyun.py lecture --course 数据科学      # 一键获取讲座字幕
```

## 缓存策略

| 数据 | 缓存时长 |
|------|----------|
| 课表 | 7 天 |
| 成绩 | 6 小时 |
| 考试 | 12 小时 |
| 作业 | 1 小时 |
| 智云搜索 | 4 小时 |
| 智云字幕 | 永久 |

缓存存储在 `cache/` 目录，可手动删除以强制刷新。

## 注意事项

- Session 会过期（通常几小时），过期后重新运行 `zju_login.py` 即可
- 智云 JWT 通过 OAuth 2.0 自动获取，极少情况下可能失败，此时需手动从浏览器复制 token
- 所有脚本输出 JSON 格式，方便程序化处理
- 凭证明文存储在本地 `data/credentials.json`，请注意安全
- **智云课堂 API（classroom.zju.edu.cn）需要校内网络环境**，校外访问会超时或被拒绝。如需在校外使用，请通过浙大 VPN 或校内代理访问。教务网和学在浙大不受此限制

## 致谢

认证和 API 逻辑翻译自 [Celechron](https://github.com/Celechron/Celechron) Flutter 项目的 Dart 代码。

## License

MIT
