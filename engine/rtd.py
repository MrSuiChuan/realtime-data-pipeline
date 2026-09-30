#!/usr/bin/env python3
# Copyright 2026 AI实战技能圈
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""rtd —— 实时数开引擎命令行。

    py -3 .rtd/engine/rtd.py setup      --project .       # 初始化运行时（含引擎自拷贝）
    py -3 .rtd/engine/rtd.py status     [--json]
    py -3 .rtd/engine/rtd.py object set --file-id … --name … --source …
    py -3 .rtd/engine/rtd.py evidence add --kind compile_receipt --from raw.json --tool … --command "…"
    py -3 .rtd/engine/rtd.py gate set   --name compile_ok --evidence <id>
    py -3 .rtd/engine/rtd.py gate set   --name debug_confirmed --user-confirm "用户原话"
    py -3 .rtd/engine/rtd.py advance    --phase debug --reason "编译过了"
    py -3 .rtd/engine/rtd.py run start|finish …
    py -3 .rtd/engine/rtd.py env check  [--json]
    py -3 .rtd/engine/rtd.py resume     --observed observed.json
    py -3 .rtd/engine/rtd.py verify

退出码：0 正常；2 = 被门或校验拒绝（不是 bug）；1 = 引擎自身错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

# stderr 也要显式设编码：argparse 的报错里含中文 choices，Windows 上默认 cp936/cp1252
# 会直接 UnicodeEncodeError（既有插件在 CI 上踩过同一个坑）。
sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402

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

ENGINE_FILES = ("core.py", "rtd.py")


def emit(payload, as_json: bool, human: str) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif human:
        print(human)


def resolve_runtime(args) -> core.Runtime:
    if getattr(args, "project", None):
        root = Path(args.project).resolve()
    else:
        root = core.find_project_root() or Path.cwd().resolve()
    return core.Runtime(root)


def install_engine(runtime: core.Runtime) -> str:
    """把引擎自拷贝进 <项目>/.rtd/engine/，并记录哈希——命令里的路径才稳定。"""
    source_dir = Path(__file__).resolve().parent
    target_dir = runtime.dir / "engine"
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    for name in ENGINE_FILES:
        src = source_dir / name
        if not src.is_file():
            continue
        dst = target_dir / name
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)
        digest.update(src.read_bytes())
    return digest.hexdigest()[:16]


def plugin_version() -> str:
    """插件清单版本；写进运行时，方便回头看"这份状态是哪版引擎/技能产生的"（RTD-027）。"""
    for rel in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = Path(__file__).resolve().parent.parent / rel
        if not path.is_file():
            continue
        try:
            version = str(json.loads(path.read_text(encoding="utf-8")).get("version") or "").strip()
        except (OSError, json.JSONDecodeError):
            continue
        if version:
            return version
    return ""


# ------------------------------------------------------------------ 子命令


def cmd_setup(args) -> int:
    runtime = resolve_runtime(args)
    runtime.root.mkdir(parents=True, exist_ok=True)
    engine_hash = install_engine(runtime)
    template = Path(__file__).resolve().parent.parent / "templates" / "config.example.json"
    result = runtime.setup(template)

    state = runtime.load_state()
    state["engine"] = {
        "hash": engine_hash,
        "plugin_version": plugin_version(),
        "installed_at": core.now_iso(),
    }
    runtime.save_state(state)

    report = core.env_status(runtime)
    payload = {**result, "engine_hash": engine_hash, "gaps": report["gaps"], "ready": report["ready"]}
    human_lines = [
        f"运行时：{runtime.dir}",
        f"引擎版本：{engine_hash}（已自拷贝到 .rtd/engine/）",
    ]
    if result["created"]:
        human_lines.append("新建：" + "、".join(result["created"]))
    if result["config_created"]:
        human_lines.append("已生成 config.json 模板——**接下来要你填执行器**（权限 0600，别提交）")
    if result["gitignore_touched"]:
        human_lines.append("已把 .rtd/ 追加进项目 .gitignore")
    if report["gaps"]:
        human_lines.append("缺口：")
        human_lines.extend(f"  - {gap}" for gap in report["gaps"])
    else:
        human_lines.append("执行器配置齐了；跑 env check 做一次只读探测确认可用")
    emit(payload, args.json, "\n".join(human_lines))
    return 0


def cmd_status(args) -> int:
    runtime = resolve_runtime(args)
    state = runtime.load_state()
    phase = state.get("phase")
    gaps = runtime.phase_gaps(state)
    limits, limit_gaps = runtime.limits()
    payload = {
        "object": state.get("object", {}),
        "phase": phase,
        "gates_satisfied": sorted(state.get("gates", {}).keys()),
        "next_gap": gaps,
        "evidence_count": len(runtime.load_evidence_index()["items"]),
        "revision": state.get("revision"),
        "updated_at": state.get("updated_at"),
        "limits_gaps": limit_gaps,
        "limits": limits,
    }
    human = [f"对象：{json.dumps(state.get('object', {}), ensure_ascii=False)}", f"阶段：{phase}"]
    if gaps:
        human.append("待补门控：")
        human.extend(f"  - {g['gate']}（{g['desc']}）" for g in gaps)
    else:
        human.append("本阶段门控已齐；可以 advance 到下一阶段")
    human.append(f"证据条数：{payload['evidence_count']}；状态版本：{payload['revision']}")
    if limit_gaps:
        human.append("限额提示：" + "；".join(limit_gaps))
    emit(payload, args.json, "\n".join(human))
    return 0


def cmd_object_set(args) -> int:
    runtime = resolve_runtime(args)
    state = runtime.load_state()
    obj = state.setdefault("object", {})
    for key, value in (
        ("file_id", args.file_id),
        ("name", args.name),
        ("source", args.source),
        ("version", args.version),
        ("instance_id", args.instance_id),
    ):
        if value:
            obj[key] = value
    obj["observed_at"] = core.now_iso()
    runtime.save_state(state)
    emit({"object": obj, "revision": state.get("revision")}, args.json, f"对象已记录：{json.dumps(obj, ensure_ascii=False)}")
    return 0


def cmd_evidence_add(args) -> int:
    runtime = resolve_runtime(args)
    item = runtime.add_evidence(
        kind=args.kind,
        source=Path(args.source).resolve(),
        tool=args.tool,
        command=args.command,
        raw_format=args.format,
    )
    human = [
        f"证据已登记：{item['id']}",
        f"  校验：{'通过' if item['validation']['ok'] else '未通过'} — {item['validation']['reason']}",
        f"  来源：{item['tool']} / {item['command']}",
    ]
    emit(item, args.json, "\n".join(human))
    return 0 if item["validation"]["ok"] else 2


def cmd_gate_set(args) -> int:
    runtime = resolve_runtime(args)
    state = runtime.load_state()
    if bool(args.evidence) == bool(args.user_confirm):
        raise core.RtError("gate_input", "必须二选一：--evidence <id> 或 --user-confirm \"原话\"")
    if args.evidence:
        record = runtime.set_gate_readback(state, args.name, args.evidence)
    else:
        record = runtime.set_gate_confirm(state, args.name, args.user_confirm, args.value)
    runtime.save_state(state)
    emit({"gate": args.name, "record": record, "phase": state.get("phase")}, args.json, f"门控已置：{args.name}（{record['source']}）")
    return 0


def cmd_advance(args) -> int:
    runtime = resolve_runtime(args)
    state = runtime.load_state()
    move = runtime.advance(state, args.phase, args.reason, allow_back=args.allow_back)
    runtime.save_state(state)
    emit(move, args.json, f"阶段推进：{move['from']} → {move['to']}")
    return 0


def cmd_run_start(args) -> int:
    runtime = resolve_runtime(args)
    state = runtime.load_state()
    request = runtime.run_start(state, args.kind, args.summary)
    emit(request, args.json, f"执行记录已开：{request['run_id']}（{args.kind}）")
    return 0


def cmd_run_finish(args) -> int:
    runtime = resolve_runtime(args)
    result = runtime.run_finish(args.run, args.status, args.trace or "", args.note or "")
    emit(result, args.json, f"执行记录已收：{result['run_id']} → {result['status']}")
    return 0


def cmd_env_check(args) -> int:
    runtime = resolve_runtime(args)
    if not runtime.exists():
        raise core.RtError("runtime_missing", "项目里还没有 .rtd/，先跑 setup")
    payload = core.env_status(runtime)
    human = ["执行器状态："]
    for row in payload["executors"]:
        human.append(f"  - {row['executor']}: {row['state']}（探测：{row['probe'] or '未探测'}）")
    if payload["gaps"]:
        human.append("缺口：")
        human.extend(f"  - {gap}" for gap in payload["gaps"])
    else:
        human.append("配置齐了。注意：认证完成与可调用要一次只读探测才算数。")
    emit(payload, args.json, "\n".join(human))
    return 0


def cmd_resume(args) -> int:
    runtime = resolve_runtime(args)
    state = runtime.load_state()
    observed = _read_observed(args.observed)
    diffs = []
    stored = state.get("object", {})
    for key, value in observed.items():
        if key in stored and str(stored[key]) != str(value):
            diffs.append({"field": key, "state": stored[key], "observed": value})
    if diffs:
        emit(
            {"resumed": False, "diffs": diffs},
            args.json,
            "续跑前对账失败：状态文件与平台回读不一致，先处理差异再继续。\n"
            + "\n".join(f"  - {d['field']}: 记录={d['state']} 实测={d['observed']}" for d in diffs),
        )
        return 2

    state["last_resume"] = {"at": core.now_iso(), "observed": observed}
    runtime.save_state(state)
    emit(
        {"resumed": True, "phase": state.get("phase"), "object": stored},
        args.json,
        f"对账通过：阶段 {state.get('phase')}，可以继续。",
    )
    return 0


def _read_observed(value: str) -> dict:
    path = Path(value)
    if path.is_file():
        raw = path.read_text(encoding="utf-8")
    else:
        raw = value
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        raise core.RtError("observed_invalid", f"--observed 既不是文件也不是合法 JSON：{err}") from err
    if not isinstance(data, dict) or not data:
        raise core.RtError("observed_invalid", "--observed 必须是非空 JSON 对象（平台回读结果）")
    return data


def cmd_verify(args) -> int:
    runtime = resolve_runtime(args)
    problems = runtime.verify()
    if problems:
        emit({"ok": False, "problems": problems}, args.json, "校验失败：\n" + "\n".join(f"  - {p}" for p in problems))
        return 2
    emit({"ok": True}, args.json, "运行时自检通过：状态、证据哈希、门控引用一致。")
    return 0


# ------------------------------------------------------------------ 入口


def build_parser() -> argparse.ArgumentParser:
    # 顶层与子命令都能接 --project/--json，写法上 `setup --project .` 与 `--project . setup` 等价。
    # 子命令里用 SUPPRESS 默认值，避免 argparse 的"子解析器默认值覆盖顶层"陷阱。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS, help="项目根目录（默认从当前目录向上找 .rtd）")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="机器可读输出")

    parser = argparse.ArgumentParser(prog="rtd", description="实时数开引擎")
    parser.add_argument("--project", help="项目根目录（默认从当前目录向上找 .rtd）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    sub = parser.add_subparsers(dest="group", required=True)

    setup = sub.add_parser("setup", parents=[common], help="初始化运行时")
    setup.set_defaults(func=cmd_setup)

    status = sub.add_parser("status", parents=[common], help="看阶段与门控缺口")
    status.set_defaults(func=cmd_status)

    obj = sub.add_parser("object", parents=[common], help="记录当前对象")
    obj_sub = obj.add_subparsers(dest="action", required=True)
    obj_set = obj_sub.add_parser("set", parents=[common])
    obj_set.add_argument("--file-id")
    obj_set.add_argument("--name")
    obj_set.add_argument("--source")
    obj_set.add_argument("--version")
    obj_set.add_argument("--instance-id")
    obj_set.set_defaults(func=cmd_object_set)

    ev = sub.add_parser("evidence", parents=[common], help="证据账本")
    ev_sub = ev.add_subparsers(dest="action", required=True)
    ev_add = ev_sub.add_parser("add", parents=[common])
    ev_add.add_argument("--kind", required=True, choices=sorted(core.EVIDENCE_RULES))
    ev_add.add_argument("--from", dest="source", required=True)
    ev_add.add_argument("--tool", required=True)
    ev_add.add_argument("--command", required=True)
    ev_add.add_argument("--format", default="json", choices=["json"])
    ev_add.set_defaults(func=cmd_evidence_add)

    gate = sub.add_parser("gate", parents=[common], help="门控键")
    gate_sub = gate.add_subparsers(dest="action", required=True)
    gate_set = gate_sub.add_parser("set", parents=[common])
    gate_set.add_argument("--name", required=True, choices=sorted(core.GATES))
    gate_set.add_argument("--evidence")
    gate_set.add_argument("--user-confirm")
    gate_set.add_argument("--value")
    gate_set.set_defaults(func=cmd_gate_set)

    adv = sub.add_parser("advance", parents=[common], help="阶段推进")
    adv.add_argument("--phase", required=True, choices=list(core.PHASES))
    adv.add_argument("--reason", default="")
    adv.add_argument("--allow-back", action="store_true")
    adv.set_defaults(func=cmd_advance)

    run = sub.add_parser("run", parents=[common], help="执行记录")
    run_sub = run.add_subparsers(dest="action", required=True)
    run_start = run_sub.add_parser("start", parents=[common])
    run_start.add_argument("--kind", required=True)
    run_start.add_argument("--summary", default="")
    run_start.set_defaults(func=cmd_run_start)
    run_finish = run_sub.add_parser("finish", parents=[common])
    run_finish.add_argument("--run", required=True)
    run_finish.add_argument("--status", required=True, choices=list(core.RUN_STATUSES))
    run_finish.add_argument("--trace")
    run_finish.add_argument("--note")
    run_finish.set_defaults(func=cmd_run_finish)

    env = sub.add_parser("env", parents=[common], help="执行器环境")
    env_sub = env.add_subparsers(dest="action", required=True)
    env_check = env_sub.add_parser("check", parents=[common])
    env_check.set_defaults(func=cmd_env_check)

    resume = sub.add_parser("resume", parents=[common], help="跨会话续跑对账")
    resume.add_argument("--observed", required=True, help="平台回读结果（JSON 文件或字面量）")
    resume.set_defaults(func=cmd_resume)

    verify = sub.add_parser("verify", parents=[common], help="运行时自检")
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except core.RtError as err:
        payload = err.as_dict()
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, **payload}, ensure_ascii=False, indent=2))
        else:
            print(f"[拒绝] {err.message}")
            if err.hint:
                print(f"       {err.hint}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
