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
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# 缺省值；真正的取值从项目配置 .rtd/config.json 的 limits 读（RTD-021）
DEFAULT_CONFIRM_WINDOW_MINUTES = 30
DEFAULT_RECORD_READ_LINES = 50

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
    # 中文写法与引擎侧 HIGH_RISK_RUN_TOKENS 对齐：命中这条还要先出现配置里的执行器名，
    # 所以不会因为正文里写了"启动"就误伤（2026-10-11 真实案例）
    "启动",
    "停止",
    "重启",
    "热更新",
    "下线",
    "取消",
    "发布",
    "上线",
    "回刷",
    "回滚",
    "部署",
)

# 引擎侧工具名里出现这些动词 = 在尝试改作业状态（RTD-018）
ENGINE_WRITE_VERBS = (
    "startjob",
    "restartjob",
    "stopjob",
    "hotstart",
    "hot_start",
    "canceljob",
    "submit",
    "deploy",
    "publish",
    "kill",
)

# 平台系 MCP 工具名里出现这些动词 = 改线上状态，同样要当次确认
MCP_WRITE_VERBS = ENGINE_WRITE_VERBS + ("offline", "backfill", "restart", "start", "stop")


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
    tool = (tool_name or "").lower()

    # 引擎侧 MCP 只读边界：不看命令串，只看工具名（RTD-018）。
    engine_name = _executor_value(root, "mcp_engine")
    if engine_name and engine_name.lower() in tool and any(verb in tool for verb in ENGINE_WRITE_VERBS):
        return Decision(
            "engine_readonly",
            f"引擎侧工具（{engine_name}）永久只读：{tool_name} 是作业变更动作。"
            "启停/发布请走平台侧执行器，并按当次确认流程；平台侧不可用时如实报告阻塞。",
        )

    # 下面这几条靠命令串判断；没有命令串（例如 MCP 调用）就跳过，别提前 return——
    # MCP 规则只看工具名（这个分支漏掉过一次，见 RTD-018）。
    if blob.strip():
        decision = _evidence_guard(command, file_path, content)
        if decision:
            return decision

        lowered = blob.lower()
        if "--yes" in lowered and not _recent_confirm(root, now):
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

    # 平台系 MCP：工具名带写动词且没有当次确认（RTD-018）
    for name in ("mcp_ops", "mcp_dev", "mcp_asset"):
        value = _executor_value(root, name)
        if value and value.lower() in tool and any(verb in tool for verb in MCP_WRITE_VERBS):
            if not _recent_confirm(root, now):
                return Decision(
                    "mcp_high_risk",
                    f"这次调用（{tool_name}）是要改线上状态的动作，但 30 分钟内没有当次确认记录。"
                    "先确认再调，或用 gate set --user-confirm 记录原话。",
                )
            break
    return None


def matches_executor(tool_name: str, root: Path) -> bool:
    """工具名是否命中配置里的执行器——MCP 工具名不含 rtd/realtime，得靠配置识别（RTD-018）。"""
    tool = (tool_name or "").lower()
    if not tool:
        return False
    return any(value.lower() in tool for value in _executor_values(root) if value)


def _executor_values(root: Path) -> list[str]:
    config = _load_config(root)
    executors = config.get("executors") if isinstance(config.get("executors"), dict) else {}
    values: list[str] = []
    for key, value in executors.items():
        if isinstance(value, dict):
            candidate = value.get("cmd") or value.get("name")
            if isinstance(candidate, str) and candidate.strip() and not candidate.strip().startswith("<"):
                values.append(candidate.strip())
        elif isinstance(value, str) and value.strip() and not value.strip().startswith("<"):
            values.append(value.strip())
    return values


def _executor_value(root: Path, key: str) -> str:
    config = _load_config(root)
    executors = config.get("executors") if isinstance(config.get("executors"), dict) else {}
    value = executors.get(key)
    if isinstance(value, dict):
        value = value.get("cmd") or value.get("name")
    text = str(value or "").strip()
    if not text or text.startswith("<"):
        return ""
    return text


def _load_config(root: Path) -> Dict[str, Any]:
    path = root / ".rtd" / "config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


# 写动词表：只有当"同段里出现写动词"时，提到证据/状态文件才算违规。
# 旧实现按"命令串里出现标记"判定，实测把只读命令也拦了（2026-10-14 测试用例 R-46）：
#   `Get-Content .rtd/_state.json -Raw`              —— 只是排查状态
#   `py -3 -c "... read_text('.rtd/_state.json')"`   —— 只读核对
# 这条门要守的是"证据只能由引擎写"，不是"谁也不许提这两个文件名"。
_MUTATOR_RE = re.compile(
    r"\b(rm|del|delete|unlink|remove|mv|move|rename|touch|truncate|write_text|write_bytes"
    r"|remove-item|removeitem|set-content|add-content|out-file|new-item|clear-content"
    r"|copy-item|copy|cp|tee|tee-object|dd)\b"
    r"|sed\s+-i|open\([^)]*['\"]w"
    r"|(?<![-\d&])>>?(?!&)",
    re.IGNORECASE,
)
# 补丁式写入的目标路径：`*** Add File: <path>` / `*** Update File: <path>` / `*** Move to: <path>`
_PATCH_TARGET_RE = re.compile(
    r"^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(.+?)\s*$"
    r"|^\*\*\*\s+Move to:\s*(.+?)\s*$",
    re.MULTILINE,
)


def _normalize_path_text(value: str) -> str:
    return str(value or "").replace("\\", "/").lower()


def _is_evidence_path(value: str) -> bool:
    text = _normalize_path_text(value)
    return any(_normalize_path_text(marker) in text for marker in EVIDENCE_MARKERS)


def _patch_targets(text: str) -> List[str]:
    """抽出补丁里涉及的每个文件路径（含 `*** Move to:` 目标）。"""
    if not text:
        return []
    found = [(match.group(1) or match.group(2) or "").strip() for match in _PATCH_TARGET_RE.finditer(text)]
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            found.append(line[6:].strip())
    seen: List[str] = []
    for item in found:
        if item and item not in seen:
            seen.append(item)
    return seen


def _evidence_guard(command: str, file_path: str, content: str) -> Optional[Decision]:
    """拦"真的在写"证据/状态文件的调用，两种命中形态：

    * 写入目标本身就是证据/状态文件（Write/Edit 的 file_path，或补丁里的目标路径）；
    * 同一命令段里既有写动词、又提到证据/状态文件（shell 重定向、Set-Content、rm…）。
    """
    message = (
        "证据与状态文件（.rtd/_evidence/、_state.json）只能由引擎写。"
        "要用 rtd.py evidence add / gate set / advance 提交，不要直接改文件。"
    )
    # 补丁文本的两个落点都要看：Claude Code 侧在 content，Codex 侧实测放在 command 里
    # （extract_strings 把 payload 的 input 当命令串）。漏一边就等于换个宿主就能绕过门。
    for target in [file_path, *_patch_targets(content), *_patch_targets(command)]:
        if target and _is_evidence_path(target):
            return Decision("evidence_write", message)
    for segment in re.split(r";|&&|\|\||\n", command or ""):
        if _is_evidence_path(segment) and _MUTATOR_RE.search(segment):
            return Decision("evidence_write", message)
    return None


def _cli_name(root: Path) -> str:
    """执行器命令名从项目配置读；读不到就返回空串（这条规则静默跳过，不猜）。"""
    return _executor_value(root, "cli")


def _recent_confirm(root: Path, now: Optional[datetime]) -> bool:
    records = root / ".rtd" / "_records" / "gates.jsonl"
    if not records.is_file():
        return False
    now = now or datetime.now().astimezone()
    window = timedelta(minutes=_limit_int(root, "confirm_window_minutes", DEFAULT_CONFIRM_WINDOW_MINUTES))
    for line in _tail(records, _limit_int(root, "record_read_lines", DEFAULT_RECORD_READ_LINES)):
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


def _limit_int(root: Path, key: str, default: int) -> int:
    """数字类阈值一律走配置；缺省回落内置值（RTD-021）。"""
    limits = _load_config(root).get("limits")
    if isinstance(limits, dict):
        value = limits.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return default


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
