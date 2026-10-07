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

"""oss_lab —— 开源实时组件的本地实验台：装、起、停、探、冒烟，一次只起一个。

    py -3 tools/oss_lab.py list
    py -3 tools/oss_lab.py plan    oss_kafka
    py -3 tools/oss_lab.py status
    py -3 tools/oss_lab.py start   oss_kafka --stop-others
    py -3 tools/oss_lab.py smoke   oss_kafka --topic rtd_lab_smoke --count 3 --out .tmp/lab/kafka
    py -3 tools/oss_lab.py stop    oss_kafka

三条设计约束：

1. **组件知识只在注册表里**：角色、构件、端口、内存、配方全部来自
   `governance/oss-components.json`；本文件不额外维护一份组件清单。安装路径与地址来自
   项目级 `.rtd/config.json` 的 `executors.*` 与 `.rtd/lab.json` 的 `lab.*`。
2. **一次只起一个重型组件**：`start` 前先看状态文件与端口探针，发现别的重型组件在跑就拒绝，
   要换组件得显式 `--stop-others`（或先 `stop`）。失败现场必须能归因到唯一一个组件。
3. **冒烟证据只认真实输出**：每条配方按顺序执行，原始 stdout/stderr 落盘；
   预期行数对不上就是失败，不允许把"没数据"和"查失败"混为一谈。

本文件不做任何隐式安装：`start` 不会替你下载，`install` 也不会替你改配置。
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue


_configure_stdio()

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PLUGIN_ROOT / "governance" / "oss-components.json"


class LabError(Exception):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class Refused(Exception):
    """守卫拒绝（不是错误）：另一个重型组件在跑。"""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


# ------------------------------------------------------------------ 注册表与配置


def load_registry(path: Path | str | None = None) -> dict:
    # argparse 传进来的是字符串；以前只用默认路径，这条分支没被测到（补用例时抓到）。
    target = Path(path) if path else REGISTRY_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise LabError(f"找不到组件注册表：{target}") from err
    except json.JSONDecodeError as err:
        raise LabError(f"组件注册表不是合法 JSON：{err}") from err
    if not isinstance(data.get("components"), list) or not data["components"]:
        raise LabError("组件注册表里没有 components 列表")
    return data


def component(registry: dict, component_id: str) -> dict:
    for item in registry["components"]:
        if item.get("id") == component_id:
            return item
    known = "、".join(str(item.get("id")) for item in registry["components"])
    raise LabError(f"注册表里没有组件：{component_id}", f"已登记：{known}")


def project_root(explicit: str | None) -> Path:
    root = Path(explicit).resolve() if explicit else Path.cwd()
    for candidate in (root, *root.parents):
        if (candidate / ".rtd").is_dir() or (candidate / "governance" / "oss-components.json").is_file():
            return candidate
    return root


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def real_value(value: Any) -> bool:
    """与引擎同一条规则：`<占位符>` 不算已配置。"""
    text = str(value or "").strip()
    if not text:
        return False
    return not (text.startswith("<") and text.endswith(">"))


class Context:
    """一次调用需要的全部输入：注册表、项目配置、变量表、状态文件。"""

    def __init__(self, root: Path, registry: dict, config: dict, lab: dict) -> None:
        self.root = root
        self.registry = registry
        self.config = config
        self.lab = lab
        # runner 非空 = 组件跑在另一个壳里（典型是 WSL）。端口探针要在那一侧做：
        # Windows 侧不一定看得见 WSL 里监听的端口，反过来也一样（实测踩过）。
        self.remote = bool(str(lab.get("runner") or "").strip())
        executors = config.get("executors") if isinstance(config.get("executors"), dict) else {}
        self.executors = executors
        state_file = str(lab.get("state_file") or ".rtd/lab-state.json")
        self.state_path = root / state_file
        self.variables: dict[str, str] = {
            "root": str(lab.get("root") or registry.get("lab", {}).get("root_default") or "~/oss"),
            "plugin_root": self._plugin_root(),
        }
        for name, value in executors.items():
            if isinstance(value, str):
                self.variables[name] = value
            elif isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(item, str):
                        self.variables[f"{name}.{key}"] = item
                    elif isinstance(item, list) and all(isinstance(part, str) for part in item):
                        # 列表值（例如一组 jar 路径）：逗号连接，`--jars` 之类正好要这个形状。
                        self.variables[f"{name}.{key}"] = ",".join(item)

    def _plugin_root(self) -> str:
        """包内工具的路径要按 runner 那一侧写；组件跑在 WSL 时 `C:\\…` 那边不存在。"""
        text = str(PLUGIN_ROOT)
        if self.remote and len(text) > 1 and text[1] == ":":
            return "/mnt/" + text[0].lower() + text[2:].replace("\\", "/")
        return text

    def lookup(self, name: str) -> str | None:
        """支持 `${oss_kafka.home}` 与 `${home}`（单组件上下文里的短名）。"""
        if name in self.variables:
            return self.variables[name]
        if "." in name:
            owner, _, key = name.partition(".")
            value = self.executors.get(owner)
            if isinstance(value, dict) and isinstance(value.get(key), str):
                return value[key]
            return None
        for value in self.executors.values():
            if isinstance(value, dict) and isinstance(value.get(name), str):
                return value[name]
        return None

    def resolve(self, text: str, extra: dict[str, str] | None = None) -> str:
        if not isinstance(text, str):
            return text
        table = dict(self.variables)
        if extra:
            table.update({key: value for key, value in extra.items() if isinstance(value, str)})
        out = text
        for key, value in table.items():
            out = out.replace("${" + key + "}", str(value))
        return out

    def gaps_for(self, spec: dict) -> list[str]:
        """组件自己声明的关键键是否填全——占位符（<…>）不算填了。"""
        name = str(spec.get("id"))
        value = self.executors.get(name)
        if not isinstance(value, dict):
            return [f"executors.{name} 整段未配置"]
        missing = [key for key in spec.get("required_keys", []) if not real_value(value.get(key))]
        return [f"executors.{name}.{key}" for key in missing]

    def read_state(self) -> dict:
        return _read_json(self.state_path)

    def write_state(self, payload: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def build_context(args) -> Context:
    root = project_root(getattr(args, "project", None))
    registry = load_registry(getattr(args, "registry", None))
    config = _read_json(root / ".rtd" / "config.json")
    lab = _read_json(root / ".rtd" / "lab.json")
    merged = dict(registry.get("lab", {}))
    merged.update({key: value for key, value in lab.items() if value not in (None, "")})
    return Context(root, registry, config, merged)


# ------------------------------------------------------------------ 执行与探针


def runner_argv(ctx: Context) -> list[str]:
    """把配置里的 runner 拆成 argv 前缀；没配就在本机 shell 里跑。"""
    raw = str(ctx.lab.get("runner") or "").strip()
    if not raw:
        return ["bash", "-lc"]
    return shlex.split(raw)


def _q(value: Any) -> str:
    """shell 引号，但把开头的 `~` 换成 `$HOME` 并留在引号外。

    两个坑都要躲：`shlex.quote('~/oss')` 会把 `~` 变成字面量；写成 `~/'oss'` 又依赖
    波浪号展开的解析时机（实测出现过落在工作目录下、名字里带 `~` 的目录）。换成
    `"$HOME"/'oss'` 两种歧义都没有。
    """
    text = str(value)
    if text == "~":
        return '"$HOME"'
    if text.startswith("~/"):
        return '"$HOME"/' + shlex.quote(text[2:])
    return shlex.quote(text)


def plugin_root_for_runner(ctx: Context) -> str:
    """包内工具在 runner 那一侧的可读路径（见 Context._plugin_root）。"""
    return ctx.variables["plugin_root"]


def run_script(ctx: Context, script: str, timeout: int = 300) -> tuple[int, str]:
    """执行一段脚本，返回 (退出码, 合并输出)。测试会替换这个函数。"""
    command = [*runner_argv(ctx), script]
    try:
        # 必须显式指定编码：组件与 runner 输出的都是 UTF-8，
        # 而 Windows 上 text=True 会按本地代码页（GBK）解码，遇到非 GBK 字节直接抛异常。
        done = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except FileNotFoundError as err:
        raise LabError(f"runner 不存在：{' '.join(command)}", "检查 .rtd/lab.json 的 runner") from err
    except subprocess.TimeoutExpired:
        return 124, f"[超时] {timeout}s 内没结束：{script}"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def probe_tcp(target: str, timeout: float = 2.0) -> tuple[bool, str]:
    host, _, port = target.rpartition(":")
    host = host or "127.0.0.1"
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, f"{target} 可连接"
    except (OSError, ValueError) as err:
        return False, f"{target} 不可连接（{type(err).__name__}）"


def probe_http(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status < 500, f"{url} → HTTP {response.status}"
    except urllib.error.HTTPError as err:
        return err.code < 500, f"{url} → HTTP {err.code}"
    except Exception as err:  # noqa: BLE001 —— 探针失败原因要原样带出去
        return False, f"{url} 探测失败（{type(err).__name__}）"


def check_tcp(ctx: Context, target: str, timeout: float = 2.0) -> tuple[bool, str]:
    """探一个 tcp 端口：配了 runner 就在 runner 那一侧探，否则本机直接探。"""
    if ctx.remote:
        host, _, port = target.rpartition(":")
        host = host or "127.0.0.1"
        script = (f"timeout {int(timeout) + 1} bash -c 'exec 3<>/dev/tcp/{host}/{port}' "
                  "&& echo RTD_TCP_OK || echo RTD_TCP_FAIL")
        code, out = run_script(ctx, script)
        ok = code == 0 and "RTD_TCP_OK" in out
        return ok, f"{target} 经 runner 探测：{'通' if ok else '不通'}"
    return probe_tcp(target, timeout)


def _probe_once(ctx: Context, spec: dict,
                extra: dict[str, str] | None = None) -> tuple[bool, list[str]]:
    ready = spec.get("ready") or {}
    details: list[str] = []
    ok = True
    for target in ready.get("tcp") or []:
        state, detail = check_tcp(ctx, ctx.resolve(str(target), extra))
        details.append(detail)
        ok = ok and state
    http = ready.get("http")
    if http:
        state, detail = probe_http(ctx.resolve(str(http), extra))
        details.append(detail)
        ok = ok and state
    probe_argv = ready.get("probe_argv")
    if probe_argv:
        argv = [ctx.resolve(str(item), extra) for item in probe_argv]
        code, _ = run_script(ctx, " ".join(_q(item) for item in argv))
        details.append(f"{' '.join(argv)} → rc {code}")
        ok = ok and code == 0
    if not details:
        details.append("注册表没给就绪探针——按「未提供探针」处理，不假装起来了")
        ok = False
    return ok, details


def probe(ctx: Context, spec: dict, extra: dict[str, str] | None = None,
          wait: bool = False) -> tuple[bool, list[str]]:
    """探就绪。`wait=True` 时按注册表的 timeout_s 反复探到就绪或超时。

    组件启动后到真正可用之间有延迟（Kafka 的 broker 注册、Flink 的 TaskManager 注册），
    一次探不通就判"起不来"会把正常的启动过程误报成失败（实测踩过）。
    """
    ready = spec.get("ready") or {}
    timeout_s = ready.get("timeout_s")
    if not wait or not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
        return _probe_once(ctx, spec, extra)
    deadline = time.monotonic() + float(timeout_s)
    result = _probe_once(ctx, spec, extra)
    while not result[0] and time.monotonic() < deadline:
        time.sleep(2)
        result = _probe_once(ctx, spec, extra)
    return result


# ------------------------------------------------------------------ 子命令


def _executor_extra(ctx: Context, spec: dict) -> dict[str, str]:
    value = ctx.executors.get(str(spec.get("id")))
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(item, str)}


def _extra(ctx: Context, args, spec: dict) -> dict[str, str]:
    """短名变量：`${home}` 这类在单组件上下文里要能解析。"""
    extra = _executor_extra(ctx, spec)
    if getattr(args, "topic", None):
        extra["topic"] = str(args.topic)
    if getattr(args, "count", None) is not None:
        extra["count"] = str(args.count)
    return extra


def cmd_list(args) -> int:
    """列出注册表里的组件、角色与构件就绪情况。"""
    ctx = build_context(args)
    rows = []
    for spec in ctx.registry["components"]:
        gaps = ctx.gaps_for(spec)
        rows.append({
            "id": spec.get("id"),
            "display": spec.get("display"),
            "role": spec.get("role"),
            "launch_mode": spec.get("launch_mode"),
            "tier": spec.get("tier"),
            "heavy": bool(spec.get("heavy")),
            "config_ref": spec.get("config_ref"),
            "configured": not gaps,
            "missing": gaps,
            "verified_on": (spec.get("verified") or {}).get("on"),
        })
    if args.json:
        print(json.dumps({"components": rows, "total": len(rows)}, ensure_ascii=False, indent=2))
        return 0
    print(f"{'组件':<18}{'角色':<15}{'形态':<9}{'层':<4}{'构件齐':<8}{'验收':<12}关键缺口")
    for row in rows:
        print(f"{row['id']:<18}{str(row['role']):<15}{str(row['launch_mode']):<9}"
              f"{str(row['tier']):<4}{('是' if row['configured'] else '否'):<8}"
              f"{(row['verified_on'] or '未验证'):<12}{'、'.join(row['missing']) or '—'}")
    return 0


def cmd_plan(args) -> int:
    """只看一条组件的起停配方与冒烟步骤，不执行任何东西。"""
    ctx = build_context(args)
    spec = component(ctx.registry, args.component)
    extra = _extra(ctx, args, spec)
    plan = {
        "component": spec.get("id"),
        "display": spec.get("display"),
        "role": spec.get("role"),
        "launch_mode": spec.get("launch_mode"),
        "tier": spec.get("tier"),
        "heavy": bool(spec.get("heavy")),
        "mem_mb": spec.get("mem_mb"),
        "ports": spec.get("ports"),
        "gaps": ctx.gaps_for(spec),
        "start": [ctx.resolve(item, extra) for item in spec.get("start") or []],
        "stop": [ctx.resolve(item, extra) for item in spec.get("stop") or []],
        "steps": [
            {"name": step.get("name"), "kind": step.get("kind"), "desc": step.get("desc")}
            for step in spec.get("smoke") or []
        ],
        "note": "start 不会替你下载；缺构件先 install。一次只起一个重型组件。",
    }
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    print(f"{plan['display']}（{plan['component']}，{plan['role']}，{plan['launch_mode']}，tier {plan['tier']}）")
    for label, key in (("启动", "start"), ("停止", "stop")):
        print(f"{label}：")
        for item in plan[key] or ["（注册表未提供）"]:
            print(f"  - {item}")
    print("冒烟：")
    for step in plan["steps"] or [{"name": "（注册表未提供）", "kind": "-", "desc": ""}]:
        print(f"  - {step.get('name')} [{step.get('kind')}] {step.get('desc') or ''}")
    if plan["gaps"]:
        print("关键缺口：" + "、".join(plan["gaps"]))
    return 0


def _target_ports(ctx: Context, spec: dict) -> set[str]:
    """一条组件用来判就绪的 tcp 端点（解析后的）。"""
    extra = _executor_extra(ctx, spec)
    ports: set[str] = set()
    for target in (spec.get("ready") or {}).get("tcp") or []:
        resolved = ctx.resolve(str(target), extra)
        if resolved and "${" not in resolved:
            ports.add(resolved)
    return ports


def _heavy_running(ctx: Context, skip: str, own_ports: set[str] | None = None) -> list[str]:
    """哪些重型组件看起来还在跑：状态文件 + 端口探针两路核对。

    **端口重叠时两路都不可信**：Doris 与 StarRocks 默认都用 9030，探到端口开着也说不清是谁的，
    只看端口会把正在跑的 Doris 误判成 StarRocks（实测踩过）。重叠就跳过这条候选。
    """
    own = own_ports or set()
    found: list[str] = []
    state = ctx.read_state()
    up = state.get("up")
    if isinstance(up, str) and up and up != skip:
        try:
            up_ports = _target_ports(ctx, component(ctx.registry, up))
        except LabError:
            up_ports = set()
        if not (up_ports & own):
            found.append(up)
    for spec in ctx.registry["components"]:
        name = str(spec.get("id"))
        if name == skip or not spec.get("heavy"):
            continue
        if _target_ports(ctx, spec) & own:
            continue
        extra = _executor_extra(ctx, spec)
        for target in (spec.get("ready") or {}).get("tcp") or []:
            resolved = ctx.resolve(str(target), extra)
            if not resolved or "${" in resolved:
                continue
            state_ok, _ = check_tcp(ctx, resolved)
            if state_ok and name not in found:
                found.append(name)
    return found


def cmd_start(args) -> int:
    """启动一个组件（重型组件一次只起一个）。"""
    ctx = build_context(args)
    spec = component(ctx.registry, args.component)
    extra = _extra(ctx, args, spec)
    gaps = ctx.gaps_for(spec)
    if gaps and not args.force:
        raise LabError("构件路径还没配全：" + "、".join(gaps),
                       "先填 .rtd/config.json；确认这条组件的 required_keys 是否写对再起")

    running = _heavy_running(ctx, str(spec.get("id")), _target_ports(ctx, spec))
    if spec.get("heavy") and running:
        if not args.stop_others:
            raise Refused(
                f"已有重型组件在跑：{'、'.join(running)}——一次只起一个",
                "先 `stop` 它，或显式加 --stop-others（会先停掉再起）",
            )
        for name in running:
            other = component(ctx.registry, name)
            for item in other.get("stop") or []:
                run_script(ctx, ctx.resolve(item, _executor_extra(ctx, other)), timeout=args.timeout)

    logs: list[str] = []
    ok = True
    if spec.get("skip_start_if_ready"):
        # 已经在跑就不重复起：判据用实验台自己的探针，不用配方里的进程名匹配——
        # 那种写法会匹配到启动器自己的命令行，永远判成"已经在跑"（实测踩过）。
        already, already_details = _probe_once(ctx, spec, extra)
        if already:
            ctx.write_state({
                "up": spec.get("id"),
                "since": datetime.now().astimezone().isoformat(timespec="seconds"),
                "probe": already_details,
            })
            payload = {"component": spec.get("id"), "started": True, "already_running": True,
                       "probe": already_details, "log": [], "state_file": str(ctx.state_path)}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print("已经在跑，跳过启动步骤：" + "；".join(already_details))
            return 0
    for item in spec.get("start") or []:
        script = ctx.resolve(item, extra)
        code, out = run_script(ctx, script, timeout=args.timeout)
        logs.append(f"$ {script}\n{out.strip()}")
        if code != 0:
            ok = False
            break
    if ok:
        ready_ok, details = probe(ctx, spec, extra, wait=True)
    else:
        ready_ok, details = False, ["未执行：启动脚本失败"]
    if ok and ready_ok:
        ctx.write_state({
            "up": spec.get("id"),
            "since": datetime.now().astimezone().isoformat(timespec="seconds"),
            "probe": details,
        })
    payload = {"component": spec.get("id"), "started": ok and ready_ok, "probe": details,
               "log": logs, "state_file": str(ctx.state_path)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for chunk in logs:
            print(chunk)
        print(("就绪：" if ready_ok else "未就绪：") + "；".join(details))
    return 0 if (ok and ready_ok) else 3


def cmd_stop(args) -> int:
    """停止一个组件并清掉状态文件里的记录。"""
    ctx = build_context(args)
    spec = component(ctx.registry, args.component)
    extra = _extra(ctx, args, spec)
    logs: list[str] = []
    ok = True
    for item in spec.get("stop") or []:
        script = ctx.resolve(item, extra)
        code, out = run_script(ctx, script, timeout=args.timeout)
        logs.append(f"$ {script}\n{out.strip()}")
        ok = ok and code == 0
    state = ctx.read_state()
    if state.get("up") == spec.get("id"):
        state["up"] = None
        state["stopped_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        ctx.write_state(state)
    payload = {"component": spec.get("id"), "stopped": ok, "log": logs}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for chunk in logs:
            print(chunk)
        print("已停" if ok else "停止脚本返回非 0，现场见上")
    return 0 if ok else 3


def cmd_status(args) -> int:
    """逐个组件探一次就绪状态；库形态的组件没有独立进程。"""
    ctx = build_context(args)
    rows = []
    for spec in ctx.registry["components"]:
        extra = _executor_extra(ctx, spec)
        ready = spec.get("ready") or {}
        if str(spec.get("launch_mode")) == "library":
            rows.append({"id": spec.get("id"), "running": None,
                         "detail": ["库形态：没有独立进程，看宿主引擎"]})
            continue
        if not (ready.get("tcp") or ready.get("http") or ready.get("probe_argv")):
            rows.append({"id": spec.get("id"), "running": None,
                         "detail": ["注册表未提供就绪探针"]})
            continue
        state, details = probe(ctx, spec, extra)
        rows.append({"id": spec.get("id"), "running": state, "detail": details})
    state = ctx.read_state()
    if args.json:
        print(json.dumps({"components": rows, "state": state}, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        mark = {True: "在跑", False: "未起", None: "不适用"}[row["running"]]
        spec = component(ctx.registry, row["id"])
        ready = spec.get("ready") or {}
        if row["running"] is not None and not (ready.get("tcp") or ready.get("http")):
            # 没有常驻进程的引擎（按需提交型）：说"可提交"比说"在跑"诚实。
            mark = "可提交" if row["running"] else "不可用"
        print(f"{row['id']:<18}{mark:<6}{'；'.join(row['detail'])}")
    if state.get("up"):
        print(f"状态文件记录：{state['up']}（{state.get('since')}）")
    return 0


def _step_script(ctx: Context, step: dict,
                 extra: dict[str, str]) -> tuple[str | None, int | None, str | None]:
    """把注册表里的冒烟步骤翻译成一段脚本；不认识的类型显式返回 None。

    返回值第三项是"数据行长什么样"的正则：命令行工具常会自己打印一行汇总
    （例如"Processed a total of N messages"），按总行数判会把汇总算成数据，
    读到 2 条也能凑够 3 行（实测踩过）。给了正则就只数匹配的行。
    """
    kind = str(step.get("kind"))
    matches = step.get("expect_stdout_matches")
    matches = ctx.resolve(str(matches), extra) if matches else None
    # 有些组件必须在自己的目录里跑（Spark 会往当前目录写 Derby 元数据库），
    # 不指定的话会把运行残渣留在调用者所在的项目里。
    cwd = ctx.resolve(str(step.get("cwd")), extra) if step.get("cwd") else ""

    def _wrap(script: str | None) -> str | None:
        if script is None or not cwd:
            return script
        return f"mkdir -p {_q(cwd)} && cd {_q(cwd)} && {script}"

    raw_expect = step.get("expect_stdout_lines")
    expect = int(raw_expect) if isinstance(raw_expect, int) else None
    if expect is None and isinstance(raw_expect, str) and raw_expect.strip().isdigit():
        expect = int(raw_expect.strip())
    if isinstance(raw_expect, str) and not raw_expect.strip().isdigit() and "${" in raw_expect:
        resolved = ctx.resolve(raw_expect, extra)
        expect = int(resolved) if resolved.strip().isdigit() else None
    if kind == "cli":
        argv = [ctx.resolve(str(item), extra) for item in step.get("argv") or []]
        if not argv:
            return None, expect, matches
        return _wrap(" ".join(_q(item) for item in argv)), expect, matches
    if kind == "shell":
        return _wrap(ctx.resolve(str(step.get("script") or ""), extra) or None), expect, matches
    if kind in {"sql", "refs"}:
        python = str(ctx.lab.get("python") or "python3")
        cli = f"{plugin_root_for_runner(ctx)}/tools/oss_cli.py"
        if kind == "sql":
            sql = ctx.resolve(str(step.get("sql") or ""), extra)
            return _wrap(f"{python} {_q(cli)} flink query -s {_q(sql)}"), expect, matches
        table = ctx.resolve(str(step.get("table") or ""), extra)
        return _wrap(f"{python} {_q(cli)} evidence refs --table {_q(table)}"), expect, matches
    return None, expect, matches


def cmd_smoke(args) -> int:
    """按注册表配方真跑一遍，原始输出落盘，行数对不上就算失败。"""
    ctx = build_context(args)
    spec = component(ctx.registry, args.component)
    extra = _extra(ctx, args, spec)
    out_dir = Path(args.out) if args.out else (ctx.root / ".tmp" / "lab" / str(spec.get("id")))
    out_dir.mkdir(parents=True, exist_ok=True)
    steps = spec.get("smoke") or []
    if not steps:
        raise LabError(f"{spec.get('id')} 没有本地冒烟配方",
                       "tier 3 组件只登记角色与配置形状——不要假装它跑过")

    results = []
    ok = True
    for step in steps:
        name = str(step.get("name"))
        kind = str(step.get("kind"))
        script, expect_lines, matches = _step_script(ctx, step, extra)
        if script is None:
            results.append({"name": name, "kind": kind, "passed": False,
                            "detail": f"本工具的配方类型还没实现：{kind}"})
            ok = False
            continue
        code, out = run_script(ctx, script, timeout=args.timeout)
        (out_dir / f"{name}.txt").write_text(script + "\n----\n" + out, encoding="utf-8")
        # runner 自己的诊断行（例如 WSL 启动时的 "wsl: ..." 提示）不是数据，
        # 不参与行数判定——否则一条提示就能把"读回 0 行"顶成"通过"。
        noise = ctx.lab.get("noise_prefixes") or ["wsl:"]
        lines = [line for line in out.splitlines()
                 if line.strip() and not any(line.lstrip().startswith(str(p)) for p in noise)]
        if matches:
            pattern = re.compile(matches)
            lines = [line for line in lines if pattern.search(line)]
        passed = code == 0
        detail = f"rc {code}，输出 {len(lines)} 行"
        if expect_lines is not None:
            passed = passed and len(lines) >= expect_lines
            detail += f"，预期 ≥ {expect_lines} 行"
        # 读数比对：把配方里声明的"应等于几"跟输出里的数字对上，
        # 免得判据只落在"有没有打印"上（那不是读回验证）。
        want = step.get("expect_stdout_value_equals")
        if want is not None:
            target = ctx.resolve(str(want), extra)
            hit = next((re.search(r"(\d+)", line) for line in lines
                        if re.search(r"(\d+)", line)), None)
            got = hit.group(1) if hit else None
            passed = passed and got == target
            detail += f"，读数 {got} 应等于 {target}"
        results.append({"name": name, "kind": kind, "passed": passed, "detail": detail,
                        "log": str(out_dir / f"{name}.txt")})
        ok = ok and passed
    payload = {"component": spec.get("id"), "passed": ok, "steps": results, "out_dir": str(out_dir)}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for row in results:
            print(f"[{'通过' if row['passed'] else '失败'}] {row['name']} —— {row['detail']}")
        print(f"原始输出：{out_dir}")
    return 0 if ok else 3


def cmd_install(args) -> int:
    """按注册表的构件信息下载并解包；不碰配置、不自动起服务。"""
    ctx = build_context(args)
    spec = component(ctx.registry, args.component)
    artifact = spec.get("artifact") or {}
    kind = str(artifact.get("kind"))
    if kind == "docker":
        # 容器形态的"安装"就是拉镜像：镜像里已经带好了组件，没有解包这一步。
        images = [ctx.resolve(str(item)) for item in artifact.get("images") or []]
        if not images:
            raise LabError(f"{spec.get('id')} 没有登记镜像", "docker 形态需要 images 列表")
        lines = ["set -e"]
        for image in images:
            lines.append(f"docker image inspect {_q(image)} > /dev/null 2>&1 || docker pull {_q(image)}")
        script = "\n".join(lines)
        code, out = run_script(ctx, script, timeout=args.timeout)
        payload = {"component": spec.get("id"), "installed": code == 0,
                   "images": images, "script": script, "log": out}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(out.strip())
            print(f"镜像：{'、'.join(images)}（rc {code}）")
        return 0 if code == 0 else 3

    dest = ctx.resolve(str(artifact.get("unpack_to") or ""))
    if not dest:
        raise LabError(f"{spec.get('id')} 的构件没有 unpack_to", "tier 3 组件没有本地配方")
    # 用 posixpath 而不是 Path：`Path("~/oss/x").parent` 在 Windows 上会给出 `~\oss`，
    # 那是另一个目录名（实测把安装包解到了工作目录下一个带 `~` 的目录里）。
    parent = _q(posixpath.dirname(dest))
    if dest.strip() in {"", "/", "~", "$HOME", ".", ".."}:
        raise LabError(f"{spec.get('id')} 的 unpack_to 不合法：{dest!r}",
                       "构件落点必须是明确的子目录，否则重装会清掉不该清的东西")
    if kind == "tgz":
        url = ctx.resolve(str(artifact.get("mirror") or "") or str(artifact.get("url") or ""))
        candidates = [ctx.resolve(str(item)) for item in
                      (artifact.get("mirror"), artifact.get("url")) if item]
        candidates = [item for item in candidates if item and not item.endswith("/")]
        if not candidates:
            raise LabError(f"{spec.get('id')} 的构件没有具体下载地址",
                           "只登记了发行目录；先人工定版再补 url")
        tarball = f"{ctx.resolve('${root}')}/{candidates[0].rsplit('/', 1)[-1]}"
        # 镜像先试、归档站兜底：镜像上没有该构件是常事，不该直接判安装失败。
        attempts = " || ".join(
            f"curl -fL --retry 3 -o {_q(tarball)} {_q(item)}" for item in candidates
        )
        script = (
            "set -e\n"
            f"mkdir -p {parent}\n"
            f"test -s {_q(tarball)} || {{ {attempts}; }}\n"
            # 先清目标目录再解包：留下上一版的文件会让插件扫描到两个版本
            # （实测 Debezium 混装 3.0.8 与 3.6.3 后，Connect 直接起不来）。
            f"rm -rf {_q(dest)}\n"
            f"tar -xzf {_q(tarball)} -C {parent}\n"
            f"test -d {_q(dest)}"
        )
    elif kind == "maven":
        coordinate = str(artifact.get("coordinate") or "")
        if not coordinate:
            raise LabError(f"{spec.get('id')} 的构件没有坐标")
        group, _, tail = coordinate.partition(":")
        name, _, pin = tail.partition(":")
        if not pin:
            raise LabError(f"{spec.get('id')} 的构件坐标没有版本：{coordinate}",
                           "jar 形态必须有确定的版本，否则拿不到唯一构件")
        url = (f"https://repo1.maven.org/maven2/{group.replace('.', '/')}/{name}/{pin}/"
               f"{name}-{pin}.jar")
        script = ("set -e\n"
                  f"mkdir -p {parent}\n"
                  f"test -s {_q(dest)} || curl -fL --retry 3 -o {_q(dest)} {_q(url)}")
    else:
        raise LabError(f"不认识的构件类型：{kind}")
    code, out = run_script(ctx, script, timeout=args.timeout)
    payload = {"component": spec.get("id"), "installed": code == 0, "dest": dest,
               "script": script, "log": out}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(out.strip())
        print(f"构件落点：{dest}（rc {code}）")
    return 0 if code == 0 else 3


# ------------------------------------------------------------------ 入口


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oss_lab", description="开源实时组件本地实验台")
    parser.add_argument("--project", help="项目根目录（默认从当前目录往上找 .rtd/）")
    parser.add_argument("--registry", help="组件注册表路径（默认仓库内 governance/oss-components.json）")
    parser.add_argument("--timeout", type=int, default=300, help="单条配方的超时秒数")
    sub = parser.add_subparsers(dest="command", required=True)

    def child(name: str) -> argparse.ArgumentParser:
        node = sub.add_parser(name)
        node.add_argument("component", nargs="?", help="组件 id，见 list")
        node.add_argument("--json", action="store_true", help="机器可读输出")
        return node

    child("list")
    plan = child("plan")
    plan.add_argument("--topic", help="冒烟用的 topic / 表名")
    plan.add_argument("--count", type=int, help="冒烟预期行数")
    start = child("start")
    start.add_argument("--stop-others", action="store_true", help="先停掉在跑的重型组件")
    start.add_argument("--force", action="store_true", help="构件没配全也照起（排查用）")
    child("stop")
    child("status")
    smoke = child("smoke")
    smoke.add_argument("--topic", default="rtd_lab_smoke", help="冒烟用的 topic / 表名")
    smoke.add_argument("--count", type=int, default=3, help="冒烟预期行数")
    smoke.add_argument("--out", help="原始输出落盘目录")
    child("install")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {
        "list": cmd_list, "status": cmd_status, "plan": cmd_plan, "start": cmd_start,
        "stop": cmd_stop, "smoke": cmd_smoke, "install": cmd_install,
    }[args.command]
    try:
        return handler(args)
    except Refused as err:
        print(f"[拒绝] {err.message}")
        if err.hint:
            print(f"[下一步] {err.hint}")
        return 4
    except LabError as err:
        print(f"[缺口] {err.message}")
        if err.hint:
            print(f"[提示] {err.hint}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
