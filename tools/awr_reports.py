#!/usr/bin/env python3
"""看台账验收报告的落盘情况：每个工作项最新一轮是哪次提交。

    py -3 tools/awr_reports.py              # 人读
    py -3 tools/awr_reports.py --json       # 机器读

命名约定：`docs/reports/<工作项小写>-completion-<提交短SHA>.json`（AWR 的 version 1 报告）。
报告**全量保留**：它们按提交 SHA 绑定证据，删掉会让历史提交上的验证无法复核。
本工具只读，不改任何文件。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "docs" / "reports"
PATTERN = re.compile(r"^(?P<item>[a-z0-9-]+)-completion-(?P<sha>[0-9a-f]{7,40})\.json$")


def collect() -> dict[str, list[str]]:
    """返回 {工作项: [提交短SHA, ...]}，按加入顺序。"""
    rounds: dict[str, list[str]] = {}
    for path in sorted(REPORTS.glob("*-completion-*.json")):
        match = PATTERN.match(path.name)
        if not match:
            continue
        item = match.group("item").upper()
        rounds.setdefault(item, []).append(match.group("sha"))
    return rounds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="只列最近 N 个提交轮次（0 = 全部）")
    args = parser.parse_args()

    rounds = collect()
    if not rounds:
        print(f"{REPORTS} 下还没有验收报告")
        return 1

    all_shas: list[str] = []
    for shas in rounds.values():
        for sha in shas:
            if sha not in all_shas:
                all_shas.append(sha)
    if args.limit:
        keep = set(all_shas[-args.limit:])
        rounds = {item: [s for s in shas if s in keep] for item, shas in rounds.items()}
        rounds = {item: shas for item, shas in rounds.items() if shas}

    payload = {
        "reports_dir": str(REPORTS.relative_to(ROOT)).replace("\\", "/"),
        "rounds": all_shas,
        "items": {
            item: {"latest": shas[-1], "all": shas, "count": len(shas)}
            for item, shas in sorted(rounds.items())
        },
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"报告目录：{payload['reports_dir']}（{len(all_shas)} 个提交轮次，{len(payload['items'])} 个工作项）")
    print()
    for item, info in payload["items"].items():
        suffix = "" if info["count"] == 1 else f"，共 {info['count']} 轮"
        print(f"{item:<10} 最新 {info['latest']}{suffix}")
    print()
    print("提示：完成校验是按提交 SHA 计的，核对某个提交要显式带上它——")
    print("      awr intake inspect --project . --source-sha <提交> --json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
