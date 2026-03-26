# ZJU Scholar

浙大学习助手，提供统一认证登录、教务数据查询、学在浙大课程与资源访问、智云课堂内容提取、CC98 论坛信息获取，并统一输出结构化 JSON。

这个仓库为 Skill 形态设计，可用于Claude code 、codex 或 openclaw。

## 功能

- 教务：课表、成绩、GPA、考试
- 学在浙大：课程列表、活动、课件、课堂互动、作业 DDL、个人资源
- 智云课堂：我的课程、视频元数据、PPT 时间轴、字幕原文、讲座纯文本
- CC98：热门帖子、帖子搜索、帖子详情、帖子楼层、热门回帖
- 自动识别校内直连与校外 WebVPN
- 统一 JSON 输出，便于脚本处理或供 AI 继续消费

## 安装

环境要求：

- Python 3.10+

安装依赖：

```bash
pip install -r scripts/requirements.txt
```

如果作为 Claude Code Skill 使用，可将项目复制或链接到 skills 目录：

```bash
cp -r . ~/.claude/skills/zju-scholar
```

```powershell
Copy-Item -Recurse . "$env:USERPROFILE\.claude\skills\zju-scholar"
```

## 快速开始

首次登录：

```bash
python scripts/zju_login.py -u 学号 -p 密码
```

查看状态：

```bash
python scripts/zju_login.py --status
```

常用查询：

```bash
python scripts/zju_academic.py courses
python scripts/zju_academic.py grades
python scripts/zju_courses.py todos
python scripts/zju_zhiyun.py lecture --course 数据科学
python scripts/zju_cc98.py hot --period weekly
```

更完整的脚本说明、参数和典型用法见 [SKILL.md](./SKILL.md)。

## 项目结构

```text
zju-scholar/
├── SKILL.md
├── README.md
├── scripts/
├── references/
├── data/
├── cache/
├── output/
└── tests/
```

## 注意事项

- Session 会过期，查询失败时先重新运行 `zju_login.py`
- CC98 搜索依赖论坛登录态，先运行 `python scripts/zju_cc98.py login --username 用户名 --password 密码`
- ZJU 凭证和 session 保存在 `data/credentials.json` / `data/session.json`，CC98 凭证和 token 保存在 `data/cc98_credentials.json` / `data/cc98_session.json`
- CC98 服务器容量有限，请只做按需查询，不要大规模爬取、批量翻页抓取或高频轮询
- 学在浙大历史课程状态字段并不稳定，已结束课程查询以脚本内部聚合逻辑为准
- 这是非官方项目，与浙江大学及相关平台无官方关联

## 致谢与参考

本项目在设计和实现过程中参考了以下开源项目的思路、接口信息或已有实践：

- [Celechron](https://github.com/Celechron/Celechron)
- [ZJU-live-better](https://github.com/5dbwat4/ZJU-live-better)
- [Learning_at_ZJU_third_client](https://github.com/YangShu233-Snow/Learning_at_ZJU_third_client)
- [ZJU-New-WebVPN.Csharp](https://github.com/Ginsenvey/ZJU-New-WebVPN.Csharp)

## License

GNU GPL v3.0
