#!/usr/bin/env python3
"""从 commands/*.md 生成 Codex 侧入口（技能 + Codex 清单）。

    py -3 tools/build_codex_surface.py            # 生成
    py -3 tools/build_codex_surface.py --check    # 只校验生成物与源一致（CI 用）

事实源是 commands/*.md（Claude Code 斜杠命令）。Codex 没有斜杠命令，用户入口是技能：
`/setup` → 技能 `rtd-setup`。生成物都带「勿手改」抬头，改流程请改命令源。

版本号的唯一来源是 .claude-plugin/plugin.json 的 version；宿主缓存需要 `+codex.<token>`
后缀，本脚本保留已有后缀，不重新发明基础版本。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ROOT / "commands"
SKILLS = ROOT / "skills"
CLAUDE_MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"

PLUGIN_NAME = "realtime-data-plugin"
PREFIX = "rtd"

INTERFACE = {
    "displayName": "Realtime Data Pipeline",
    "shortDescription": "实时数据开发流水线 + 阶段硬门控",
    "longDescription": (
        "把实时任务研发工艺翻成状态机加硬门控：引用元表是否已发布、编译是否真过、"
        "发布校验是否通过、启停是否有当次确认，全部以机器证据为准。执行器（平台 CLI、"
        "研发/运维/资产/引擎各域 MCP）与限额从项目级配置读取，仓库内只有占位示例，可直接对外分享。"
        "Claude Code 用斜杠命令，Codex 用 rtd-* 技能。"
    ),
    "developerName": "AI实战技能圈",
    "category": "Productivity",
    "capabilities": ["Instructions", "Lifecycle hooks", "Write"],
    "defaultPrompt": [
        "初始化实时数开插件并接入我的平台",
        "把这段实时 SQL 建任务、编译、调试、发布",
        "巡检这个实时任务的上下游，出一份带证据的报告",
    ],
    "brandColor": "#0F766E",
}

HEADER = (
    "> 本文件由 `tools/build_codex_surface.py` 从 `commands/{source}` 生成，请勿手改。\n"
    "> 改流程请改命令源文件后重跑生成器。\n"
    "> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。\n"
)


def load_base_version() -> str:
    data = json.loads(CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    version = str(data.get("version") or "").strip()
    if not version:
        raise SystemExit(f"{CLAUDE_MANIFEST} 缺 version")
    return version


def summarize(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            body = line[2:].strip()
            # 去掉「# rtd-setup ... — 说明」里的命令名与破折号，留下说明
            body = re.sub(rf"^{PREFIX}-\S+\s*", "", body)
            body = re.sub(r"^[—\-–:：\s]+", "", body)
            return body or line[2:].strip()
    return ""


def build_skill(name: str, source_text: str) -> str:
    summary = summarize(source_text)
    description = f"{summary}（Codex 入口，等价于 /{name}）" if summary else f"Codex 入口，等价于 /{name}"
    body = HEADER.format(source=Path(name).name + ".md") + "\n" + source_text.rstrip() + "\n"
    front = f"---\nname: {PREFIX}-{name}\ndescription: {description}\n---\n\n"
    return front + f"# {PREFIX}-{name}（Codex 版 `/{name}`）\n\n" + body


def build_codex_manifest() -> str:
    claude = json.loads(CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    base = str(claude["version"])
    suffix = ""
    if CODEX_MANIFEST.is_file():
        old = str(json.loads(CODEX_MANIFEST.read_text(encoding="utf-8")).get("version", ""))
        if old.startswith(base) and old != base:
            suffix = old[len(base):]
    manifest = {
        "name": PLUGIN_NAME,
        "version": base + suffix,
        "description": claude.get("description", ""),
        "author": claude.get("author", {}),
        "license": claude.get("license", "MIT"),
        "keywords": claude.get("keywords", []),
        "skills": "./skills/",
        "interface": INTERFACE,
    }
    hooks = ROOT / "hooks" / "claude-codex-hooks.json"
    if hooks.is_file():
        manifest["hooks"] = "./hooks/claude-codex-hooks.json"
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    sources = sorted(p for p in COMMANDS.glob("*.md")) if COMMANDS.is_dir() else []
    if not sources:
        print(f"没有可生成的命令源：{COMMANDS}")
        return 1

    planned: dict[Path, str] = {}
    for src in sources:
        planned[SKILLS / f"{PREFIX}-{src.stem}" / "SKILL.md"] = build_skill(src.stem, src.read_text(encoding="utf-8"))
    planned[CODEX_MANIFEST] = build_codex_manifest()

    stale = []
    for path, content in planned.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        if check:
            stale.append(path.relative_to(ROOT).as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"写入 {path.relative_to(ROOT).as_posix()}")

    if check:
        if stale:
            print("生成物与命令源不一致（跑一次生成器再提交）：")
            for item in stale:
                print(f"  - {item}")
            return 1
        print(f"生成物与命令源一致（{len(sources)} 个命令）。")
        return 0

    print(f"完成：{len(sources)} 个命令 → 技能。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
