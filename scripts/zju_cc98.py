"""zju_cc98.py — CC98 论坛 thin wrapper（委托给 cc98-cli）

CC98 论坛功能由独立的 [CC98-CLI](https://github.com/Lucent-Snow/CC98-CLI) 提供。
本文件只提供与 zju-scholar 其它子命令一致的入口（python3 zju_cc98.py ...），
所有参数透传给 cc98 CLI。

安装 CC98-CLI:
    npm install -g cc98-cli

首次使用:
    cc98 login            # 交互式登录，token 存到 ~/.cc98-cli/
    python3 zju_cc98.py search "课程"   # 等价于 cc98 search "课程"

可用子命令:
    python3 zju_cc98.py <cc98 子命令> [args...]

详细命令清单与 JSON 输出说明见 references/cc98-cli.md。
本文件不再维护任何 CC98 接口实现——所有能力跟随 CC98-CLI 升级。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent


def _cc98_cli_installed() -> bool:
    return shutil.which("cc98") is not None


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__, file=sys.stderr)
        if not _cc98_cli_installed():
            print(
                '\n{"ok": false, "error": "cc98-cli 未安装。请先运行: npm install -g cc98-cli"}',
                file=sys.stderr,
            )
            return 1
        print("\n所有可用子命令：", file=sys.stderr)
        subprocess.run(["cc98", "--help"])
        return 0

    if not _cc98_cli_installed():
        print(
            '{"ok": false, "platform": "cc98", "error": "cc98-cli 未安装。请先运行: npm install -g cc98-cli"}',
            file=sys.stderr,
        )
        return 1

    # Pass every argument through unchanged; cc98 CLI owns its own arg parser.
    result = subprocess.run(["cc98", *sys.argv[1:]])
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
