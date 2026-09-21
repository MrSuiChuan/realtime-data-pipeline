#!/usr/bin/env python3
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

DEFAULT_LIMITS = {
    "scan_budget_s": 120,
    "tool_calls": 60,
    "inflight": 3,
    "external_nodes": 30,
    "poll_interval_s": 10,
    "poll_timeout_s": 300,
    "read_chunk_lines": 2000,
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

        item = {
            "id": evidence_id,
            "kind": kind,
            "file": stored.relative_to(self.dir).as_posix(),
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "tool": tool,
            "command": command,
            "observed_at": payload.get("observed_at"),
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
        if index_target < index_current and not allow_back:
            raise RtError("phase_back", f"{current} → {target} 是回跳，需要 --allow-back 与理由")
        if index_target == index_current:
            raise RtError("phase_same", f"已经在 {current}")
        if index_target > index_current + 1 and not allow_back:
            raise RtError("phase_skip", f"{current} → {target} 跨了中间阶段；逐阶段推进或在 --allow-back 下说明理由")
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
        """对象版本变了以后，旧证据一律作废（只做能确定的那部分判断）。"""
        object_version = str(state.get("object", {}).get("version") or "")
        if not object_version:
            return False
        recorded = str(item.get("object_version") or "")
        return bool(recorded) and recorded != object_version


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
    """执行器三态：配置存在 / 已探测 / 未知。引擎不主动调平台。"""
    config = runtime.load_config()
    executors = config.get("executors") if isinstance(config.get("executors"), dict) else {}
    rows = []
    gaps = []
    for name in ("cli", "mcp_dev", "mcp_ops", "mcp_asset", "mcp_engine"):
        value = executors.get(name)
        if isinstance(value, dict):
            configured = _real_value(value.get("cmd"))
            probe = value.get("verified_at")
        else:
            configured = _real_value(value)
            probe = None
        if not configured:
            gaps.append(f"executors.{name} 未配置")
        rows.append(
            {
                "executor": name,
                "configured": configured,
                "probe": probe or None,
                "state": "配置存在" if configured else "缺失",
            }
        )
    storage = executors.get("storage") if isinstance(executors.get("storage"), dict) else {}
    for name in ("log_cli", "light_db_cli"):
        if not _real_value(storage.get(name)):
            gaps.append(f"executors.storage.{name} 未配置")
    limits, limit_gaps = runtime.limits()
    gaps.extend(limit_gaps)
    return {
        "executors": rows,
        "limits": limits,
        "gaps": gaps,
        "ready": not gaps,
        "note": "认证完成与当前会话可调用需要一次只读探测才能判定；本命令不做任何平台调用。",
    }


def _real_value(value: Any) -> bool:
    """占位符（<…>）不算配置——否则"生成了模板"会被误报成"执行器齐了"。"""
    text = str(value or "").strip()
    if not text:
        return False
    return not (text.startswith("<") and text.endswith(">"))
