# CC98-CLI 速查

本 Skill 的 CC98 论坛功能通过独立的 [CC98-CLI](https://github.com/Lucent-Snow/CC98-CLI) 提供。
本文件是 CC98-CLI 在 zju-scholar 场景下的用法说明，不替代 CC98-CLI 自己的文档（`cc98 <cmd> --help`）。

## 安装与登录

```bash
npm install -g cc98-cli        # 需要 Node.js 20+
cc98 login                      # 交互登录，token 存到 ~/.cc98-cli/
cc98 --help                     # 查看所有命令
```

多账号：

```bash
cc98 account list               # 列出已保存账号
cc98 account use <name>         # 切换当前账号
python3 zju_cc98.py me -a <name>   # 在 zju-scholar 入口下指定账号
```

> 校外网络：先 `cc98 vpn login` 走 WebVPN。CC98-CLI 在请求时会自动判别。

## 与 zju-scholar 的关系

`scripts/zju_cc98.py` 是一个 thin wrapper，把所有参数透传给 `cc98`：

```bash
python3 scripts/zju_cc98.py search "课程"     # 等价于 cc98 search "课程"
python3 scripts/zju_cc98.py me
python3 scripts/zju_cc98.py topic 12345
```

wrapper 不再维护任何 CC98 接口实现，能力跟随 CC98-CLI 升级。

## 命令索引

### 论坛 / 版块

| 命令 | 说明 |
|---|---|
| `cc98 forum index` | 论坛首页配置（置顶、热门版块） |
| `cc98 forum boards` | 所有版块列表 |
| `cc98 forum card-stat` | 论坛卡片统计 |
| `cc98 board <id> [--from n] [--size n]` | 版块内的帖子（分页） |
| `cc98 board list` | 版块摘要列表 |
| `cc98 board info <id>` | 版块详细信息 |
| `cc98 board topics <id> [--from n] [--size n] [--best]` | 版块帖子（`--best` 拉精华） |
| `cc98 board favorite add\|remove <id>` | 收藏 / 取消收藏版块 |

### 帖子浏览

| 命令 | 说明 |
|---|---|
| `cc98 topic <id> [--from n] [--size n]` | 帖子详情（默认带前几楼） |
| `cc98 topic <id> --meta` | 仅元信息（不拉楼层） |
| `cc98 topic <id> --posts` | 仅楼层列表 |
| `cc98 topic new [--from n] [--size n]` | 最新帖子 |
| `cc98 topic random [--size n]` | 随机帖子 |
| `cc98 topic recommendation [--size n]` | 推荐帖子 |
| `cc98 topic recent [--me \| --user id] [--from n] [--size n]` | 某用户/我的最近帖子 |
| `cc98 topic basic <ids...>` | 批量查帖子元信息 |
| `cc98 topic search <keyword> [--from n] [--size n]` | 帖子搜索（带 boardId 等上下文） |
| `cc98 topic vote <id>` | 投票类帖子的票数 |
| `cc98 topic is-favorite <id>` | 是否已收藏 |

### 搜索

| 命令 | 说明 |
|---|---|
| `cc98 search <keyword>` | 全文搜索帖子标题/内容 |

### 用户

| 命令 | 说明 |
|---|---|
| `cc98 user me` | 当前用户信息（与 `cc98 me` 等价） |
| `cc98 user profile <id>` | 用户公开资料 |
| `cc98 user basic <ids...>` | 批量查用户基本信息 |
| `cc98 user list <ids...>` | 批量查用户列表 |
| `cc98 user followers [--from n] [--size n]` | 粉丝 |
| `cc98 user followees [--from n] [--size n]` | 关注 |
| `cc98 user moment [--from n] [--size n]` | 关注的人发的帖子 |
| `cc98 user favorite-updates [--from n] [--size n]` | 收藏更新 |
| `cc98 user favorite-groups` | 收藏分组 |
| `cc98 user search <name>` | 搜索用户 |
| `cc98 user unread` | 未读消息数 |
| `cc98 user browse-history [--from n] [--size n]` | 浏览历史 |
| `cc98 me` / `cc98 me signin` | 当前用户 / 每日签到 |

### 消息

| 命令 | 说明 |
|---|---|
| `cc98 message unread` | 未读计数 |
| `cc98 message recent [--from n] [--size n]` | 最近联系人 |
| `cc98 message history <user-id> [--from n] [--size n]` | 与某人的聊天记录 |
| `cc98 message send <user-id> <content>` | 发站内信 |

### 通知

| 命令 | 说明 |
|---|---|
| `cc98 notice system [--from n] [--size n]` | 系统通知 |
| `cc98 notice at [--from n] [--size n]` | @ 我的 |
| `cc98 notice reply [--from n] [--size n]` | 回复我的 |

### 互动（写操作）

| 命令 | 说明 |
|---|---|
| `cc98 topic create <board-id> <title> <content>` | 发新帖 |
| `cc98 topic reply <topic-id> <content>` | 回帖 |
| `cc98 topic favorite add <topic-id> [group-id]` | 收藏 |
| `cc98 topic favorite remove <topic-id>` | 取消收藏 |
| `cc98 topic favorite [--group id] [--order n] [--from n] [--size n]` | 列出收藏 |
| `cc98 board favorite add\|remove <id>` | 收藏版块 |
| `cc98 user follow\|unfollow <id>` | 关注 / 取关 |
| `cc98 post like <post-id>` / `cc98 post dislike <post-id>` | 点赞 / 倒赞 |
| `cc98 post reaction-state <post-id>` | 查看点赞状态 |
| `cc98 post rate-reasons <type>` | 评分理由列表 |

### 缓存

| 命令 | 说明 |
|---|---|
| `cc98 cache stats` | 缓存统计 |
| `cc98 cache cleanup` | 清理过期缓存 |
| `cc98 cache clear [all\|memory\|file]` | 清空缓存 |

### WebVPN

| 命令 | 说明 |
|---|---|
| `cc98 vpn login [username] [password]` | 登录 WebVPN |
| `cc98 vpn logout` | 注销 |
| `cc98 vpn status` | 当前状态 |
| `cc98 vpn test` | 测试连通性 |
| `cc98 vpn mode [auto\|vpn\|direct]` | 切换模式 |

### 其它

| 命令 | 说明 |
|---|---|
| `cc98 tui` | 进入 TUI 交互界面 |
| `cc98 update` | 检查更新 |

## 输出格式

**所有命令默认输出 JSON**（到 stdout）。错误以非零退出码 + stderr 表示。

```bash
# 例：当前用户
$ cc98 me
{
  "id": 783985,
  "name": "...",
  "postCount": 2,
  ...
}

# 例：搜索
$ cc98 search "ZJU"
[
  { "id": 6525102, "boardId": 226, "title": "...", "time": "...", ... },
  ...
]

# 例：分页
$ cc98 topic 12345 --from 20 --size 20
{ ... }
```

错误信号：

| 现象 | 含义 |
|---|---|
| 退出码 ≠ 0 | 命令执行失败（看 stderr） |
| stderr: "Token expired" / "Unauthorized" | 重新 `cc98 login` |
| stderr: "VPN not logged in" | 校外网络，先 `cc98 vpn login` |

## 与 zju-scholar 其它模块的差异

zju-scholar 的其它模块（教务、学在浙大、智云、图书馆）输出**统一 JSON 包装**：

```json
{
  "ok": true,
  "platform": "...",
  "feature": "...",
  "source": "live",
  "data": { ... }
}
```

CC98 子命令**不**使用这种包装——直接透传 CC98-CLI 的 JSON。如果你的脚本要消费 CC98 输出，请按裸 JSON 处理，不要假设有 `ok` / `data` 字段。

## 不再提供的功能

zju-scholar 早期版本（≤ 0.5）的 zju_cc98.py 中有几个功能 CC98-CLI 未提供，已移除：

- 按周期（weekly/monthly/history）拉取热门帖
- 帖子内热回帖（hot posts within topic）
- 编辑帖子（CC98-CLI 的 `cc98 post` 只支持 like/dislike，不支持 edit）

如需这些能力，请用 CC98 网页版。
