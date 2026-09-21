#!/usr/bin/env python3
"""在两个宿主/平台之间切换 hook 启动器。

    py -3 tools/adapt_hooks.py --check     # 只检查（CI 用，不写文件）
    py -3 tools/adapt_hooks.py --write      # 按本机可用解释器改写 hooks/*.json

两个坑写在前面：
1. Windows 是 `py -3`，macOS/Linux 是 `python3`，写死哪一个都会在另一边失败；
2. 本脚本会往 stdout 打印中文——GitHub 的 Windows runner 默认 cp1252，
   不显式设 UTF-8 会 UnicodeEncodeError 直接红（既有插件踩过）。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
HOOK_FILES = (ROOT / "hooks" / "hooks.json", ROOT / "hooks" / "claude-codex-hooks.json")
LAUNCHERS = ("py -3", "python3")


def detect_launcher() -> str:
    if shutil.which("py"):
        return "py -3"
    if shutil.which("python3"):
        return "python3"
    if shutil.which("python"):
        return "python"
    return ""


def launchers_in(text: str) -> list[str]:
    return [name for name in LAUNCHERS if f'"{name} ' in text or f"{name} \"" in text]


def main() -> int:
    check_only = "--check" in sys.argv
    target = detect_launcher()
    problems: list[str] = []

    for path in HOOK_FILES:
        if not path.is_file():
            problems.append(f"缺 hook 配置：{path.relative_to(ROOT).as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        try:
            json.loads(text)
        except json.JSONDecodeError as err:
            problems.append(f"{path.name} 不是合法 JSON：{err}")
            continue
        found = launchers_in(text)
        if not found:
            problems.append(f"{path.name} 里没找到已知启动器（{', '.join(LAUNCHERS)}）")
        if not check_only and target and found and found != [target]:
            new_text = text
            for old in found:
                new_text = new_text.replace(old, target)
            path.write_text(new_text, encoding="utf-8", newline="\n")
            print(f"{path.name}: {', '.join(found)} → {target}")

    if check_only:
        for problem in problems:
            print(f"[FAIL] {problem}")
        if problems:
            return 1
        print(f"hook 启动器检查通过（本机可用：{target or '未探测到'}；配置：" + "、".join(
            f"{path.name}={','.join(launchers_in(path.read_text(encoding='utf-8'))) or '无'}"
            for path in HOOK_FILES
            if path.is_file()
        ) + "）")
        return 0

    if not target:
        print("本机未探测到 py/python3，未改写任何文件。")
        return 0
    if not problems:
        print("hook 配置无需改动。")
    else:
        for problem in problems:
            print(f"[WARN] {problem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
