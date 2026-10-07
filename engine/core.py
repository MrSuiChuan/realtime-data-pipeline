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

"""实时数开引擎（runtime core）。

职责只有四件：**运行时目录**、**阶段门控**、**证据账本**、**执行记录**。
它不调用任何平台，也不改任何线上状态——写操作由执行器（平台 CLI / 各域 MCP）执行，
引擎负责"要求什么证据、记录了什么、门是否真的开了"。

诚实边界（写在最前面，别在别处再声明一遍）：

* 引擎能验证的是**证据文件的存在、哈希、必填字段、时间与类型匹配**；
  它**不能**证明那份原始输出真的来自平台。
* 因此 readback 类证据必须带 `tool` / `command` / `observed_at` 三要素，缺一即拒收；
  伪造这三样是**人**的责任边界，不是引擎能兜住的——这条写进 SECURITY.md 与验证记录。
* 引擎不会自动填时间、自动加 `--yes`、自动切换执行器。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
RUNTIME_DIR = ".rtd"
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024

PHASES: Tuple[str, ...] = (
    "discover",
    "design",
    "build",
    "debug",
    "configure",
    "submit",
    "publish",
    "start",
)

# 门控键登记表。kind=readback 的必须挂平台回读证据；kind=confirm 的必须挂当次确认原话。
GATES: Dict[str, Dict[str, Any]] = {
    "refs_published": {
        "phase": "design",
        "kind": "readback",
        "evidence": "refs_readback",
        "desc": "引用元表已发布版本回读（存在开发版不算）",
    },
    "compile_ok": {
        "phase": "build",
        "kind": "readback",
        "evidence": "compile_receipt",
        "desc": "编译终态回执",
    },
    "debug_confirmed": {
        "phase": "debug",
        "kind": "confirm",
        "desc": "调试模式选择与当次确认",
    },
    "sla_decided": {
        "phase": "configure",
        "kind": "confirm",
        "desc": "SLA 决策（明确跳过也算决策）",
    },
    "submit_ok": {
        "phase": "submit",
        "kind": "readback",
        "evidence": "submit_receipt",
        "desc": "提交终态回执",
    },
    "publish_ok": {
        "phase": "publish",
        "kind": "readback",
        "evidence": "publish_receipt",
        "desc": "发布终态回执 + 发布对象回读",
    },
    "start_confirmed": {
        "phase": "start",
        "kind": "confirm",
        "desc": "启动当次确认（高风险动作）",
    },
    "source_stopped": {
        "phase": "start",
        "kind": "confirm",
        "desc": "迁移场景：原任务已停止（声明，需另附状态回读）",
    },
    "reset_time": {
        "phase": "start",
        "kind": "confirm",
        "value_required": True,
        "desc": "用户确认的恢复点/重置时间（禁止自动取当前时间）",
    },
}

RUN_STATUSES = (
    "未提交",
    "已受理",
    "进行中",
    "失败",
    "仅保存",
    "已部署待验证",
    "已验证",
)

# 改线上状态的动作：执行记录结束时必须留追踪 ID（宪法第 3、9 条）
HIGH_RISK_RUN_TOKENS = (
    "start",
    "restart",
    "hot-update",
    "hot_update",
    "stop",
    "offline",
    "cancel",
    "publish",
    "backfill",
    "rollback",
    "deploy",
)

DEFAULT_LIMITS = {
    "scan_budget_s": 120,
    "tool_calls": 60,
    "inflight": 3,
    "external_nodes": 30,
    "poll_interval_s": 10,
    "poll_timeout_s": 300,
    "read_chunk_lines": 2000,
    "confirm_window_minutes": 30,
    "record_read_lines": 50,
}

# 执行器登记表：路径（平台 / 开源）+ 判定"已配置"所需的关键键。
# keys 为空表示该执行器的值本身就是命令名/服务名（字符串或 {name, cmd} 形态）。
# 平台那半是平台无关的常量，写在代码里；开源那半是**注册表驱动的**（见下）。
EXECUTOR_SPECS: Dict[str, Dict[str, Any]] = {
    "cli": {"path": "platform", "keys": ["cmd"]},
    "mcp_dev": {"path": "platform", "keys": []},
    "mcp_ops": {"path": "platform", "keys": []},
    "mcp_asset": {"path": "platform", "keys": []},
    "mcp_engine": {"path": "platform", "keys": []},
}

OSS_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "governance" / "oss-components.json"
# 注册表读不出来时不能静默变成"没有开源执行器"——那是把配置错误伪装成"没配"。
OSS_REGISTRY_ERROR = ""


def _oss_executor_specs(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """开源执行器的登记**单一来源**：governance/oss-components.json 里 tier 1/2 的组件。

    以前这里是手写的一份副本（oss_flink / oss_paimon / oss_fluss）。加一个组件要同时改
    引擎、执行器契约、能力矩阵、配置模板四处，且没有任何检查把它们绑在一起——注册表一扩，
    这四处必然漂移（RTD-038）。tier 3 的组件只登记角色与配置形状、没有本地配方，
    不参与"两条路选一条配全"的判定，否则开源路径永远判不成"配全"。
    """
    global OSS_REGISTRY_ERROR
    target = path or OSS_REGISTRY_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except OSError as err:
        OSS_REGISTRY_ERROR = f"读不到开源组件注册表：{target}（{type(err).__name__}）"
        return {}
    except json.JSONDecodeError as err:
        OSS_REGISTRY_ERROR = f"开源组件注册表不是合法 JSON：{target}（{err}）"
        return {}
    OSS_REGISTRY_ERROR = ""
    specs: Dict[str, Dict[str, Any]] = {}
    for item in data.get("components", []):
        if not isinstance(item, dict) or item.get("tier") == 3:
            continue
        name = item.get("id")
        if not isinstance(name, str) or not name:
            continue
        specs[name] = {
            "path": "oss",
            "keys": [str(key) for key in item.get("required_keys") or []],
            "role": item.get("role"),
            "display": item.get("display"),
        }
    return specs


EXECUTOR_SPECS.update(_oss_executor_specs())

PATH_HINTS = {
    "platform": "平台路径：至少把 executors.cli.cmd（或某个 mcp_* 服务名）填上",
    "oss": "开源路径：按 governance/oss-components.json 里 tier 1/2 组件的 required_keys 配（动过哪个就必须配全哪个，没动过的不算缺口）",
}

# 证据类型登记表：payload 必填字段 + 通过条件。
EVIDENCE_RULES: Dict[str, Dict[str, Any]] = {
    "refs_readback": {
        "required": ["tables", "observed_at"],
        "check": "refs_all_published",
        "desc": "引用元表回读：tables 里每张表都要 published=true",
    },
    "compile_receipt": {
        "required": ["status", "observed_at"],
        "check": "status_success",
        "desc": "编译回执：status 必须表示终态成功",
    },
    "submit_receipt": {
        "required": ["status", "observed_at"],
        "check": "status_success",
        "desc": "提交回执：status 必须表示终态成功",
    },
    "publish_receipt": {
        "required": ["status", "observed_at", "object_readback"],
        "check": "status_success",
        "desc": "发布回执：status 终态成功，且带发布对象回读",
    },
}

SUCCESS_WORDS = ("success", "succeeded", "active", "ok", "true", "已发布", "成功")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RtError(Exception):
    """引擎拒绝执行（不是 bug，是门）。"""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def as_dict(self) -> Dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        return payload


# ---------------------------------------------------------------- 运行时定位


def find_project_root(start: Optional[Path] = None) -> Optional[Path]:
    """从 start 向上找带 .rtd 的目录；找不到返回 None。"""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / RUNTIME_DIR).is_dir():
            return candidate
    return None


class Runtime:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.dir = self.root / RUNTIME_DIR
        self.state_path = self.dir / "_state.json"
        self.config_path = self.dir / "config.json"
        self.evidence_dir = self.dir / "_evidence"
        self.evidence_index = self.evidence_dir / "index.json"
        self.records_dir = self.dir / "_records"
        self.runs_dir = self.dir / "_runs"
        self.snapshots_dir = self.dir / "_snapshots"

    # ---- 基础读写

    def exists(self) -> bool:
        return self.state_path.is_file()

    def require(self) -> None:
        if not self.exists():
            raise RtError(
                "runtime_missing",
                f"未找到运行时：{self.state_path}",
                "先在项目里跑 rtd-setup 初始化",
            )

    def load_state(self) -> Dict[str, Any]:
        self.require()
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise RtError("state_corrupt", f"_state.json 不是合法 JSON：{err}") from err
        if state.get("schema_version") != SCHEMA_VERSION:
            raise RtError(
                "state_schema",
                f"状态文件 schema_version={state.get('schema_version')}，引擎期望 {SCHEMA_VERSION}",
            )
        return state

    def save_state(self, state: Dict[str, Any]) -> None:
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated_at"] = now_iso()
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, self.state_path)

    def load_config(self) -> Dict[str, Any]:
        if not self.config_path.is_file():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise RtError("config_invalid", f"config.json 不是合法 JSON：{err}") from err

    def limits(self) -> Tuple[Dict[str, int], List[str]]:
        config = self.load_config()
        limits = dict(DEFAULT_LIMITS)
        gaps: List[str] = []
        raw = config.get("limits")
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in limits and isinstance(value, int) and value > 0:
                    limits[key] = value
        else:
            gaps.append("config.json 缺 limits 段，当前用内置保守默认值")
        return limits, gaps

    def append_record(self, name: str, payload: Dict[str, Any]) -> None:
        self.records_dir.mkdir(parents=True, exist_ok=True)
        payload = {"at": now_iso(), **payload}
        with (self.records_dir / f"{name}.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # ---- 初始化

    def setup(self, template: Path) -> Dict[str, Any]:
        created: List[str] = []
        for path in (self.dir, self.evidence_dir, self.records_dir, self.runs_dir, self.snapshots_dir):
            if not path.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                created.append(path.relative_to(self.root).as_posix())

        if not self.state_path.is_file():
            state = {
                "schema_version": SCHEMA_VERSION,
                "project_root": str(self.root),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "revision": 0,
                "object": {},
                "phase": PHASES[0],
                "phase_history": [],
                "gates": {},
            }
            self.save_state(state)
            created.append(self.state_path.relative_to(self.root).as_posix())

        config_created = False
        if not self.config_path.is_file() and template.is_file():
            shutil.copyfile(template, self.config_path)
            try:
                os.chmod(self.config_path, 0o600)
            except OSError:
                pass
            config_created = True
            created.append(self.config_path.relative_to(self.root).as_posix())

        gitignore_touched = self._ensure_gitignore()
        return {
            "created": created,
            "config_created": config_created,
            "gitignore_touched": gitignore_touched,
            "root": str(self.root),
        }

    def _ensure_gitignore(self) -> bool:
        path = self.root / ".gitignore"
        line = f"{RUNTIME_DIR}/"
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if any(item.strip() in {line, RUNTIME_DIR} for item in existing.splitlines()):
            return False
        block = "" if (not existing or existing.endswith("\n")) else "\n"
        block += "# 实时数开运行时（状态、证据、执行记录、配置）\n" + line + "\n"
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(block)
        return True

    # ---- 证据

    def load_evidence_index(self) -> Dict[str, Any]:
        if not self.evidence_index.is_file():
            return {"schema_version": SCHEMA_VERSION, "items": []}
        try:
            data = json.loads(self.evidence_index.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise RtError("evidence_index_corrupt", f"证据索引损坏：{err}") from err
        data.setdefault("items", [])
        return data

    def save_evidence_index(self, index: Dict[str, Any]) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_index.write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    def find_evidence(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        for item in self.load_evidence_index()["items"]:
            if item.get("id") == evidence_id:
                return item
        return None

    def add_evidence(
        self,
        kind: str,
        source: Path,
        tool: str,
        command: str,
        raw_format: str = "json",
    ) -> Dict[str, Any]:
        rule = EVIDENCE_RULES.get(kind)
        if rule is None:
            raise RtError("evidence_kind", f"未知证据类型：{kind}", "可用的：" + ", ".join(sorted(EVIDENCE_RULES)))
        if not source.is_file():
            raise RtError("evidence_missing", f"证据源文件不存在：{source}")
        data = source.read_bytes()
        if not data.strip():
            raise RtError("evidence_empty", "证据文件是空的；空文件不能当证据")
        if len(data) > MAX_EVIDENCE_BYTES:
            raise RtError("evidence_too_large", f"证据超过 {MAX_EVIDENCE_BYTES // 1024 // 1024} MiB")
        if not tool.strip() or not command.strip():
            raise RtError("evidence_attribution", "必须写清 tool 与 command（这份输出是什么工具、哪条命令产生的）")
        if raw_format != "json":
            raise RtError(
                "evidence_format",
                f"{kind} 要求结构化输出",
                "让执行器以 JSON 输出（多数 CLI 有 --json / 结构化返回；MCP 本来就是结构化）后重试",
            )
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise RtError("evidence_format", f"证据不是合法 JSON：{err}") from err
        if not isinstance(payload, dict):
            raise RtError("evidence_format", "证据 JSON 顶层必须是对象")

        missing = [field for field in rule["required"] if field not in payload]
        if missing:
            raise RtError(
                "evidence_fields",
                f"{kind} 缺必填字段：{', '.join(missing)}",
                rule["desc"],
            )

        ok, reason = _validate_payload(kind, payload, rule)
        evidence_id = f"{kind}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        stored = self.evidence_dir / f"{evidence_id}.json"
        stored.write_bytes(data)

        # 记录注册时的对象身份（文件级 ID + 版本）：换对象或换版本后，这条证据要能被判为过期
        # （RTD-016 只比版本，RTD-025 补上对象身份）。空值不参与比较，不误伤。
        try:
            current_object = self.load_state().get("object", {})
        except RtError:
            current_object = {}
        object_version = str(current_object.get("version") or "")
        object_file_id = str(current_object.get("file_id") or "")

        item = {
            "id": evidence_id,
            "kind": kind,
            "file": stored.relative_to(self.dir).as_posix(),
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "tool": tool,
            "command": command,
            "observed_at": payload.get("observed_at"),
            "object_version": object_version or None,
            "object_file_id": object_file_id or None,
            "added_at": now_iso(),
            "validation": {"ok": ok, "reason": reason},
        }
        index = self.load_evidence_index()
        index["items"].append(item)
        self.save_evidence_index(index)
        self.append_record("evidence", {"evidence_id": evidence_id, "kind": kind, "ok": ok, "reason": reason})
        return item

    # ---- 门控

    def gates_for_phase(self, phase: str) -> List[str]:
        return [name for name, spec in GATES.items() if spec["phase"] == phase]

    def phase_gaps(self, state: Dict[str, Any], phase: Optional[str] = None) -> List[Dict[str, str]]:
        phase = phase or state.get("phase", PHASES[0])
        gaps: List[Dict[str, str]] = []
        for name in self.gates_for_phase(phase):
            if name in state.get("gates", {}):
                continue
            spec = GATES[name]
            gaps.append({"gate": name, "kind": spec["kind"], "desc": spec["desc"]})
        return gaps

    def set_gate_readback(self, state: Dict[str, Any], name: str, evidence_id: str) -> Dict[str, Any]:
        spec = GATES.get(name)
        if spec is None:
            raise RtError("gate_unknown", f"未知门控键：{name}")
        if spec["kind"] != "readback":
            raise RtError(
                "gate_kind",
                f"{name} 是确认类门控，不能挂证据文件；要用 --user-confirm",
                spec["desc"],
            )
        item = self.find_evidence(evidence_id)
        if item is None:
            raise RtError("gate_evidence", f"找不到证据：{evidence_id}")
        if item["kind"] != spec["evidence"]:
            raise RtError(
                "gate_evidence_kind",
                f"{name} 需要 {spec['evidence']} 类证据，拿到的是 {item['kind']}",
            )
        if not item.get("validation", {}).get("ok"):
            raise RtError(
                "gate_evidence_failed",
                f"证据未通过校验：{item['validation'].get('reason')}",
            )
        if self._evidence_stale(state, name, item):
            raise RtError(
                "gate_evidence_stale",
                "对象的版本/提交已经变了，这条证据过期；重新采集再设门",
            )
        record = {
            "source": "platform_readback",
            "evidence_id": item["id"],
            "evidence_sha256": item["sha256"],
            "tool": item["tool"],
            "command": item["command"],
            "observed_at": item.get("observed_at"),
            "set_at": now_iso(),
        }
        state.setdefault("gates", {})[name] = record
        self.append_record("gates", {"gate": name, "action": "set", **record})
        return record

    def set_gate_confirm(
        self,
        state: Dict[str, Any],
        name: str,
        quote: str,
        value: Optional[str] = None,
    ) -> Dict[str, Any]:
        spec = GATES.get(name)
        if spec is None:
            raise RtError("gate_unknown", f"未知门控键：{name}")
        if spec["kind"] != "confirm":
            raise RtError(
                "gate_kind",
                f"{name} 是回读类门控，必须挂平台证据；确认不能替代它",
                spec["desc"],
            )
        quote = (quote or "").strip()
        if not quote:
            raise RtError("gate_quote", "必须原样记录用户的当次确认原话；空话不算确认")
        if spec.get("value_required"):
            value = (value or "").strip()
            if not value:
                raise RtError(
                    "gate_value",
                    f"{name} 需要用户给出的具体值（例如恢复点时间）",
                    "引擎不会替你填当前时间",
                )
            if _looks_like_now(value):
                raise RtError(
                    "gate_value_now",
                    f"{name} 的值看起来就是当前时间；用户没确认过的时间不能当恢复点",
                )
        record = {
            "source": "user_confirm",
            "quote": quote,
            "value": value,
            "set_at": now_iso(),
        }
        state.setdefault("gates", {})[name] = record
        self.append_record("gates", {"gate": name, "action": "set", **record})
        return record

    def advance(self, state: Dict[str, Any], target: str, reason: str, allow_back: bool = False) -> Dict[str, Any]:
        current = state.get("phase", PHASES[0])
        if target not in PHASES:
            raise RtError("phase_unknown", f"未知阶段：{target}", "可用：" + ", ".join(PHASES))
        index_current, index_target = PHASES.index(current), PHASES.index(target)
        reason = (reason or "").strip()
        if index_target < index_current and not allow_back:
            raise RtError("phase_back", f"{current} → {target} 是回跳，需要 --allow-back 与理由")
        if index_target == index_current:
            raise RtError("phase_same", f"已经在 {current}")
        if index_target > index_current + 1 and not allow_back:
            raise RtError("phase_skip", f"{current} → {target} 跨了中间阶段；逐阶段推进或在 --allow-back 下说明理由")
        # 回跳与跳阶段都是非常规动作：必须写清为什么（RTD-026）。空理由等于没留痕。
        if (index_target < index_current or index_target > index_current + 1) and not reason:
            raise RtError(
                "phase_reason",
                f"{current} → {target} 是非顺序推进，必须给出理由（--reason）",
                "写清触发原因与后续动作；这条理由会落进 phases 记录",
            )
        if index_target > index_current:
            gaps = self.phase_gaps(state, current)
            if gaps:
                raise RtError(
                    "phase_gates",
                    f"{current} 阶段门未满足：" + "、".join(g["gate"] for g in gaps),
                    "；补证据后重试，不要直接跳阶段",
                )
        history = state.setdefault("phase_history", [])
        history.append({"from": current, "to": target, "at": now_iso(), "reason": reason or ""})
        state["phase"] = target
        self.append_record("phases", {"from": current, "to": target, "reason": reason or ""})
        return {"from": current, "to": target}

    # ---- 执行记录

    def run_start(self, state: Dict[str, Any], kind: str, summary: str) -> Dict[str, Any]:
        if not kind.strip():
            raise RtError("run_kind", "必须说明这次操作是什么（--kind）")
        run_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        request = {
            "run_id": run_id,
            "kind": kind,
            "summary": summary,
            "phase": state.get("phase"),
            "object": state.get("object", {}),
            "started_at": now_iso(),
        }
        (run_dir / "request.json").write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        self.append_record("runs", {"run_id": run_id, "action": "start", "kind": kind, "summary": summary})
        return request

    def run_finish(
        self,
        run_id: str,
        status: str,
        trace_id: str,
        note: str = "",
    ) -> Dict[str, Any]:
        run_dir = self.runs_dir / run_id
        if not run_dir.is_dir():
            raise RtError("run_missing", f"没有这次执行记录：{run_id}")
        if status not in RUN_STATUSES:
            raise RtError("run_status", f"状态词不在枚举里：{status}", "可用：" + " / ".join(RUN_STATUSES))

        kind = ""
        request_file = run_dir / "request.json"
        if request_file.is_file():
            try:
                kind = str(json.loads(request_file.read_text(encoding="utf-8")).get("kind") or "")
            except json.JSONDecodeError:
                kind = ""
        if _is_high_risk_run(kind) and not (trace_id or "").strip():
            raise RtError(
                "run_trace",
                f"这次执行是高风险动作（{kind}），结束时要留下追踪 ID",
                "拿不到追踪 ID 说明这次调用没被平台受理——如实记「已受理/失败」，不要留空",
            )

        result = {
            "run_id": run_id,
            "status": status,
            "trace_id": trace_id,
            "note": note,
            "finished_at": now_iso(),
        }
        (run_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        self.append_record("runs", {"action": "finish", **result})
        return result

    def latest_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.records_dir.is_dir():
            return []
        lines = (self.records_dir / "runs.jsonl")
        if not lines.is_file():
            return []
        items = []
        for line in lines.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items

    # ---- 校验

    def verify(self) -> List[str]:
        problems: List[str] = []
        state = self.load_state()
        index = self.load_evidence_index()
        by_id = {item["id"]: item for item in index["items"]}

        for item in index["items"]:
            path = self.dir / item["file"]
            if not path.is_file():
                problems.append(f"证据文件丢失：{item['id']}（{item['file']}）")
                continue
            actual = sha256_bytes(path.read_bytes())
            if actual != item["sha256"]:
                problems.append(f"证据被改动：{item['id']}（哈希不符）")

        for name, record in state.get("gates", {}).items():
            if record.get("source") == "platform_readback":
                evidence_id = record.get("evidence_id")
                if evidence_id not in by_id:
                    problems.append(f"门控 {name} 挂的证据不在索引里：{evidence_id}")
                    continue
                if by_id[evidence_id]["sha256"] != record.get("evidence_sha256"):
                    problems.append(f"门控 {name} 的证据哈希与索引不一致")
        return problems

    def _evidence_stale(self, state: Dict[str, Any], gate: str, item: Dict[str, Any]) -> bool:
        """换对象或换版本以后，旧证据一律作废（只做能确定的那部分判断）。"""
        current = state.get("object", {}) if isinstance(state.get("object"), dict) else {}

        recorded_file_id = str(item.get("object_file_id") or "")
        current_file_id = str(current.get("file_id") or "")
        if recorded_file_id and current_file_id and recorded_file_id != current_file_id:
            return True

        recorded_version = str(item.get("object_version") or "")
        current_version = str(current.get("version") or "")
        if recorded_version and current_version and recorded_version != current_version:
            return True
        return False


def _validate_payload(kind: str, payload: Dict[str, Any], rule: Dict[str, Any]) -> Tuple[bool, str]:
    check = rule["check"]
    if check == "refs_all_published":
        tables = payload.get("tables")
        if not isinstance(tables, list) or not tables:
            return False, "tables 必须是非空数组"
        bad = [t.get("name", "?") for t in tables if not t.get("published")]
        if bad:
            return False, "这些引用表还没发布：" + "、".join(str(name) for name in bad)
        return True, f"{len(tables)} 张引用表全部已发布"
    if check == "status_success":
        status = str(payload.get("status", "")).strip().lower()
        if status in {word.lower() for word in SUCCESS_WORDS}:
            return True, f"终态成功（{payload.get('status')}）"
        return False, f"终态不是成功：{payload.get('status')!r}"
    if kind == "publish_receipt":
        readback = payload.get("object_readback")
        if not isinstance(readback, dict) or not readback:
            return False, "object_readback 必须是发布后回读到的对象信息"
    return True, "已校验"


def _looks_like_now(value: str) -> bool:
    """用户给的恢复点如果与"当前时间"过于接近，说明是自动填的。"""
    digits = re.findall(r"\d", value)
    if len(digits) < 10:
        return False
    now = datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
        return abs((parsed - now).total_seconds()) < 300
    return False


def env_status(runtime: Runtime) -> Dict[str, Any]:
    """执行器三态：配置存在 / 已探测 / 未知。引擎不主动调平台。

    模型是**两条路选一条配全**：平台路径（cli / 各域 MCP）与开源路径（Flink / Paimon / Fluss）。
    以前只认平台那条，配了开源执行器的人会看到一堆误导性的"平台执行器未配置"缺口（RTD-036）。
    """
    config = runtime.load_config()
    executors = config.get("executors") if isinstance(config.get("executors"), dict) else {}

    rows: List[Dict[str, Any]] = []
    for name, spec in EXECUTOR_SPECS.items():
        value = executors.get(name)
        filled, missing = _executor_keys(value, spec["keys"])
        # 判定"用户是否开始配这条执行器"看**主键**（keys 的第一个）：
        # 模板里 rest_endpoint / warehouse 这类带默认值的键是真值，不能当成已经开始配置。
        primary = spec["keys"][0] if spec["keys"] else None
        started = bool(filled) and (primary is None or primary in filled)
        probe = value.get("verified_at") if isinstance(value, dict) else None
        rows.append({
            "executor": name,
            "path": spec["path"],
            "role": spec.get("role"),
            "configured": not missing and bool(filled),
            "started": started,
            "missing": missing,
            "probe": probe or None,
            "state": "配置存在" if (not missing and filled) else ("部分配置" if filled else "缺失"),
        })

    storage = executors.get("storage") if isinstance(executors.get("storage"), dict) else {}
    storage_gaps = []
    for name in ("log_cli", "light_db_cli"):
        if not _real_value(storage.get(name)):
            storage_gaps.append(f"executors.storage.{name} 未配置")

    gaps: List[str] = []
    path_state: Dict[str, Dict[str, Any]] = {}
    for path in ("platform", "oss"):
        path_rows = [row for row in rows if row["path"] == path]
        # 判定看**已开始的子集**：动过的组件必须配全，没动过的不算缺口。
        # 旧写法对开源路径用 all(...)，注册表一扩（Kafka / Spark / 湖表…）就会把
        # "只配 Flink + Fluss"的人误报成没配齐——注册表越大越不准（RTD-038）。
        started_rows = [row for row in path_rows if row["started"]]
        missing = [f"executors.{row['executor']}.{key}"
                   for row in started_rows for key in row["missing"]]
        path_state[path] = {
            "started": bool(started_rows),
            "complete": bool(started_rows) and not missing,
            "started_components": [row["executor"] for row in started_rows],
            "missing": missing,
        }
        if missing:
            gaps.append(f"{path} 路径配了一半：缺 " + "、".join(missing))

    if not any(item["started"] for item in path_state.values()):
        gaps.append("两条路都没配置 —— " + PATH_HINTS["platform"] + "；或 " + PATH_HINTS["oss"])
    if OSS_REGISTRY_ERROR:
        gaps.append(OSS_REGISTRY_ERROR + "；开源路径的执行器清单因此是空的")

    limits, limit_gaps = runtime.limits()
    gaps.extend(limit_gaps)
    return {
        "executors": rows,
        "paths": path_state,
        "limits": limits,
        "gaps": gaps,
        "storage_gaps": storage_gaps,
        "ready": any(item["complete"] for item in path_state.values()),
        "note": "认证完成与当前会话可调用需要一次只读探测才能判定；本命令不做任何平台调用。",
    }


def _executor_keys(value: Any, keys: List[str]) -> Tuple[List[str], List[str]]:
    """返回（已填字段, 缺失字段）。keys 为空时看值本身。"""
    if not keys:
        if isinstance(value, dict):
            filled = [k for k in ("cmd", "name") if _real_value(value.get(k))]
            return filled, [] if filled else ["<值>"]
        return (["<值>"] if _real_value(value) else []), ([] if _real_value(value) else ["<值>"])
    if not isinstance(value, dict):
        return [], list(keys)
    filled = [key for key in keys if _real_value(value.get(key))]
    return filled, [key for key in keys if key not in filled]


def _real_value(value: Any) -> bool:
    """占位符（<…>）不算配置——否则"生成了模板"会被误报成"执行器齐了"。"""
    text = str(value or "").strip()
    if not text:
        return False
    return not (text.startswith("<") and text.endswith(">"))


def _is_high_risk_run(kind: str) -> bool:
    lowered = (kind or "").lower()
    return any(token in lowered for token in HIGH_RISK_RUN_TOKENS)


# ── 跨插件契约：知识库（记忆）插件的知识索引 ────────────────────────────────
#
# 生产端 = knowledge-base-plugin 的发布流程；两侧各自对着同一份 schema 断言
# （本仓库的断言在 tests/test_kb_contract.py，生产端在它自己的 ConsumerContractTests）。
#
# 索引形状：{"documents": [{"uri", "domain", "layer", "tables", "abstract"}]}
# 消费侧只强制 uri 以 knowledge.uri_prefix 开头，不断言路径形状——
# 生产端目前写 domains/、消费侧种子数据写 domain/，这个差异两侧都知情，不在这里纠正。
KB_INDEX_CANDIDATES: Tuple[Path, ...] = (
    Path(".rtd") / "mock" / "kb" / "index.json",        # 本插件的运行目录（生产端支持后优先）
    Path(".data-dev") / "mock" / "kb" / "index.json",   # 离线插件的运行目录（生产端当前实际写这里）
)
DEFAULT_URI_PREFIX = "viking://resources/"

# 消费侧真正会读的字段；生产端改字段名时这条契约会红。
KB_DOCUMENT_FIELDS: Tuple[str, ...] = ("uri", "domain", "layer", "tables", "abstract")


class KnowledgeIndex:
    """只读知识索引：按域/表查口径，且**只认受管前缀下的知识源**。

    为什么要有前缀这条铁律：索引是外部插件写进来的，若不加限制，
    `read` 就变成一个"随便读什么 uri 都行"的接口——那就等于把知识来源交给写入方任意决定。
    """

    def __init__(self, runtime: "Runtime") -> None:
        config = runtime.load_config()
        knowledge = config.get("knowledge") if isinstance(config.get("knowledge"), dict) else {}
        prefix = str(knowledge.get("uri_prefix") or DEFAULT_URI_PREFIX).rstrip("/")
        self.uri_prefix = prefix + "/"
        configured = str(knowledge.get("index_path") or "").strip()
        self.candidates = ([Path(configured)] if configured
                           else [runtime.root / item for item in KB_INDEX_CANDIDATES])
        self.path = next((item for item in self.candidates if item.is_file()), self.candidates[0])

    def documents(self) -> List[Dict[str, Any]]:
        """读索引里的文档列表；缺失或坏 JSON 一律当"没有"，不抛异常也不编内容。"""
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        docs = data.get("documents") if isinstance(data, dict) else None
        return [item for item in (docs or []) if isinstance(item, dict)]

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """按域、表名或摘要模糊查。空查询返回空列表——不做"没给条件就全给你"。"""
        needle = (query or "").strip().lower()
        if not needle:
            return []
        hits: List[Dict[str, Any]] = []
        for doc in self.documents():
            haystack = " ".join(str(doc.get(key) or "") for key in KB_DOCUMENT_FIELDS)
            haystack += " " + " ".join(str(item) for item in doc.get("tables") or [])
            if needle in haystack.lower():
                hits.append(doc)
        return hits[:limit]

    def read(self, uri: str) -> str:
        """读一条知识源的摘要；uri 不在受管前缀下 → 拒绝。"""
        text = str(uri or "").strip()
        if not text.startswith(self.uri_prefix):
            raise RtError(
                "knowledge_uri_rejected",
                f"知识源不在受管前缀下：{text or '(空)'}（只认 {self.uri_prefix} 开头的 uri）",
                "用 knowledge search 返回的 uri；本插件不读受管前缀之外的任何知识源",
            )
        for doc in self.documents():
            if str(doc.get("uri")) == text:
                return str(doc.get("abstract") or "")
        return ""

    def status(self) -> Dict[str, Any]:
        return {
            "uri_prefix": self.uri_prefix,
            "index": str(self.path),
            "index_exists": self.path.is_file(),
            "document_count": len(self.documents()),
            "candidates": [str(item) for item in self.candidates],
        }
