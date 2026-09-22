#!/usr/bin/env python3
"""evals 跑分器（结构校验 / 导出评分表 / 汇总得分）。

    py -3 tools/run_evals.py --check                    # CI：只做结构与完整性校验
    py -3 tools/run_evals.py --export score.md          # 导出人工/Agent 评分表
    py -3 tools/run_evals.py --score scored.json        # 汇总已填好的评分

**它不调用任何模型。**语义判分（"这段回答是否真的守住了门"）由人或 Agent 做，
机器只保证三件事：用例结构完整、每条都被评过、失败的用例必须写理由。
这不是能力缺失，是刻意划界——机器能验的只有书名号里的东西。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

def _configure_stdio() -> None:
    """把 stdout/stderr 设成 UTF-8。

    捕获流（pytest、某些宿主）没有 reconfigure —— 直接调用会让整个模块导入失败，
    所以这里一律带兜底：宁可输出编码不完美，也不能让模块导入崩掉（CI 上踩过）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue


_configure_stdio()


ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"
REQUIRED_CASE_FIELDS = ("prompt", "expected_output", "expectations")


def load_suites() -> list[dict]:
    suites = []
    for path in sorted(EVALS_DIR.glob("evals-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise SystemExit(f"{path.name} 不是合法 JSON：{err}")
        data["_file"] = path.name
        suites.append(data)
    return suites


def check(suites: list[dict]) -> list[str]:
    problems: list[str] = []
    if not suites:
        problems.append("evals/ 下没有 evals-*.json")
    seen_suites: set[str] = set()
    for suite in suites:
        name = str(suite.get("suite") or "")
        if not name:
            problems.append(f"{suite['_file']} 缺 suite 字段")
        elif name in seen_suites:
            problems.append(f"{suite['_file']} 的 suite 名重复：{name}")
        seen_suites.add(name)
        if not str(suite.get("purpose") or "").strip():
            problems.append(f"{suite['_file']} 缺 purpose（这份 eval 想守什么门）")
        cases = suite.get("cases")
        if not isinstance(cases, list) or not cases:
            problems.append(f"{suite['_file']} 没有用例")
            continue
        prompts: set[str] = set()
        for index, case in enumerate(cases):
            label = f"{suite['_file']}#{index}"
            if not isinstance(case, dict):
                problems.append(f"{label} 不是对象")
                continue
            for field in REQUIRED_CASE_FIELDS:
                value = case.get(field)
                if field == "expectations":
                    if not isinstance(value, list) or not value:
                        problems.append(f"{label} 的 expectations 必须是非空数组")
                    elif not all(str(item).strip() for item in value):
                        problems.append(f"{label} 有空的 expectation")
                elif not str(value or "").strip():
                    problems.append(f"{label} 缺 {field}")
            prompt = str(case.get("prompt") or "")
            if prompt:
                if prompt in prompts:
                    problems.append(f"{label} 与同套件内另一条 prompt 完全重复")
                prompts.add(prompt)
    return problems


def export_markdown(suites: list[dict]) -> str:
    lines = [
        "# evals 评分表",
        "",
        "用法：逐条读 prompt，给出回答，对照 expectations 判定通过与否，把结论填进 `--score` 用的 JSON。",
        "",
        "评分 JSON 形状：`{\"<suite>#<index>\": {\"pass\": true|false, \"note\": \"...\"}}`；判 false 必须写 note。",
        "",
    ]
    for suite in suites:
        lines.append(f"## {suite['suite']}（{suite['_file']}）")
        lines.append("")
        lines.append(str(suite.get("purpose") or "").strip())
        lines.append("")
        for index, case in enumerate(suite.get("cases") or []):
            lines.append(f"### {suite['suite']}#{index}")
            lines.append("")
            lines.append(f"- prompt：{case.get('prompt')}")
            lines.append(f"- 期望：{case.get('expected_output')}")
            lines.append("- 判定点：")
            for item in case.get("expectations") or []:
                lines.append(f"  - [ ] {item}")
            lines.append("- 判定：`pass: ______`  note：______")
            lines.append("")
    return "\n".join(lines) + "\n"


def summarize(suites: list[dict], scored: dict) -> tuple[list[str], str]:
    problems: list[str] = []
    total = 0
    passed = 0
    lines: list[str] = []
    for suite in suites:
        name = suite["suite"]
        cases = suite.get("cases") or []
        suite_pass = 0
        for index in range(len(cases)):
            key = f"{name}#{index}"
            total += 1
            entry = scored.get(key)
            if not isinstance(entry, dict):
                problems.append(f"缺评分：{key}")
                continue
            if not isinstance(entry.get("pass"), bool):
                problems.append(f"{key} 的 pass 必须是 true/false")
                continue
            if entry["pass"]:
                suite_pass += 1
                passed += 1
            elif not str(entry.get("note") or "").strip():
                problems.append(f"{key} 判为不通过，必须写 note 说明哪条判定点没守住")
        lines.append(f"- {name}: {suite_pass}/{len(cases)}")
    extra = sorted(set(scored) - {f"{s['suite']}#{i}" for s in suites for i in range(len(s.get('cases') or []))})
    for key in extra:
        problems.append(f"评分表里有不存在的用例：{key}")
    rate = (passed / total * 100) if total else 0.0
    report = "\n".join([
        "evals 汇总",
        *lines,
        f"总计：{passed}/{total} 通过（{rate:.0f}%）",
    ])
    return problems, report


def main() -> int:
    args = sys.argv[1:]
    suites = load_suites()

    if not args or "--check" in args:
        problems = check(suites)
        for problem in problems:
            print(f"[FAIL] {problem}")
        if problems:
            print(f"\nevals 结构校验未通过：{len(problems)} 条")
            return 1
        cases = sum(len(s.get("cases") or []) for s in suites)
        print(f"evals 结构校验通过：{len(suites)} 套，{cases} 条用例")
        return 0

    if "--export" in args:
        target = Path(args[args.index("--export") + 1]) if len(args) > args.index("--export") + 1 else Path("evals-score.md")
        problems = check(suites)
        if problems:
            for problem in problems:
                print(f"[FAIL] {problem}")
            return 1
        target.write_text(export_markdown(suites), encoding="utf-8", newline="\n")
        print(f"评分表已写出：{target}")
        return 0

    if "--score" in args:
        index = args.index("--score")
        if index + 1 >= len(args):
            print("--score 需要一个 JSON 文件路径")
            return 2
        path = Path(args[index + 1])
        if not path.is_file():
            print(f"找不到评分文件：{path}")
            return 2
        scored = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(scored, dict):
            print("评分文件顶层必须是对象")
            return 2
        problems, report = summarize(suites, scored)
        print(report)
        if problems:
            print()
            for problem in problems:
                print(f"[FAIL] {problem}")
            return 1
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
