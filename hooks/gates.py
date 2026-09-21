"""PreToolUse 的判定逻辑（纯函数，便于单测）。

只管三件事，管不了的一律明说：

* **证据保护**：`.rtd/_evidence/` 与 `_state.json` 只能由引擎写；
* **`--yes` 自行追加**：没有近期的当次确认记录就不许加；
* **高风险动作**：启停/发布/回刷这类动词，没有近期确认记录就拦。

管不了的：执行器是不是真的调了平台、MCP 调用有没有越权——那属于宿主与服务端，
hook 看不到。这条边界写在 SECURITY.md，不要在别处暗示它能兜住。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

CONFIRM_WINDOW_MINUTES = 30

EVIDENCE_MARKERS = (".rtd/_evidence", ".rtd\\_evidence", "/_state.json", "\\_state.json", ".rtd/_state")

RUN_SUBCOMMANDS = (
    "run start",
    "run finish",
    "gate set",
    "evidence add",
    "advance",
    "status",
    "verify",
    "env check",
)

HIGH_RISK_WORDS = (
    "--start",
    " --stop",
    "--restart",
    "--hot-start",
    "--hot-update",
    "--offline",
    "--cancel-deploy",
    "--publish",
    "--backfill",
)


@dataclass
class Decision:
    gate: str
    reason: str
    blocked: bool = True


def decide(
    tool_name: str,
    command: str,
    file_path: str,
    content: str,
    root: Path,
    now: Optional[datetime] = None,
) -> Optional[Decision]:
    """返回 None = 放行；返回 Decision = 拦截。"""
    blob = " ".join(part for part in (command, file_path, content) if part)
    if not blob.strip():
        return None

    decision = _evidence_guard(blob)
    if decision:
        return decision

    lowered = blob.lower()
    if "--yes" in lowered:
        if not _recent_confirm(root, now):
            return Decision(
                "yes_flag",
                "命令里带了 --yes，但 30 分钟内没有当次确认记录。"
                "先让用户确认，再用 gate set --user-confirm 记录原话；不要替用户加 --yes。",
            )

    cli = _cli_name(root)
    if cli and cli.lower() in lowered and any(word in lowered for word in HIGH_RISK_WORDS):
        if not _recent_confirm(root, now):
            return Decision(
                "high_risk",
                f"这是改线上状态的动作（{cli} 启停/发布类）。"
                "要求：展示对象与影响 → 用户当次确认 → gate set --user-confirm 记录原话，然后才能执行。",
            )
    return None


def _evidence_guard(blob: str) -> Optional[Decision]:
    lowered = blob.lower()
    for marker in EVIDENCE_MARKERS:
        if marker.lower() in lowered:
            return Decision(
                "evidence_write",
                "证据与状态文件（.rtd/_evidence/、_state.json）只能由引擎写。"
                "要用 rtd.py evidence add / gate set / advance 提交，不要直接改文件。",
            )
    return None


def _cli_name(root: Path) -> str:
    """执行器命令名从项目配置读；读不到就返回空串（这条规则静默跳过，不猜）。"""
    for path in (root / ".rtd" / "config.json",):
        if not path.is_file():
            continue
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cli = config.get("executors", {}).get("cli")
        if isinstance(cli, dict):
            name = str(cli.get("cmd") or "").strip()
            if name:
                return name
        elif isinstance(cli, str) and cli.strip():
            return cli.strip()
    return ""


def _recent_confirm(root: Path, now: Optional[datetime]) -> bool:
    records = root / ".rtd" / "_records" / "gates.jsonl"
    if not records.is_file():
        return False
    now = now or datetime.now().astimezone()
    window = timedelta(minutes=CONFIRM_WINDOW_MINUTES)
    for line in _tail(records, 50):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("source") != "user_confirm":
            continue
        stamp = _parse(item.get("at") or item.get("set_at"))
        if stamp and now - stamp <= window:
            return True
    return False


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return stamp


def _tail(path: Path, lines: int) -> Sequence[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return text.splitlines()[-lines:]


def extract_strings(payload: Dict[str, Any]) -> tuple[str, str, str]:
    """从不同宿主的 payload 形状里捞 command / file_path / content。"""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("toolInput") if isinstance(payload.get("toolInput"), dict) else {}

    command = ""
    for key in ("command", "cmd", "script", "input"):
        value = tool_input.get(key) or payload.get(key)
        if isinstance(value, str) and value.strip():
            command = value
            break

    file_path = ""
    for key in ("file_path", "path", "target_file", "filename"):
        value = tool_input.get(key) or payload.get(key)
        if isinstance(value, str) and value.strip():
            file_path = value
            break

    content = ""
    for key in ("content", "new_string", "patch", "text"):
        value = tool_input.get(key) or payload.get(key)
        if isinstance(value, str) and value.strip():
            content = value
            break
    return command, file_path, content


def gated(tool_name: str) -> bool:
    lowered = (tool_name or "").lower()
    if lowered in {
        "bash",
        "shell",
        "shell_command",
        "local_shell",
        "exec_command",
        "executecommand",
        "cli",
        "write",
        "edit",
        "multiedit",
        "apply_patch",
        "applypatch",
        "patch",
        "notebookedit",
    }:
        return True
    return any(part in lowered for part in ("rtd", "realtime"))
