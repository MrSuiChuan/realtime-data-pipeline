#!/usr/bin/env python3
"""PreToolUse：硬门控（decision:block）。

惰性导入：不相关的工具走快速通道，只有需要门控的调用才付解析成本
（进程启动 + 导入的开销在宿主 hook 超时里是真实成本）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import emit, fail_open, load_payload, project_root, trace_payload  # noqa: E402


def block_output(decision) -> dict:
    """Codex / Claude Code 的 PreToolUse 输出 schema 是 additionalProperties:false。

    多一个键就可能被宿主判为非法输出并静默放行，所以严格只给这几个键。
    """
    message = f"[realtime-data-plugin:{decision.gate}] 工具调用被硬门拦截。{decision.reason}"
    return {
        "decision": "block",
        "reason": message,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        },
    }


def main() -> None:
    payload = load_payload()
    trace_payload("PreToolUse", payload)
    tool_name = str(payload.get("tool_name") or payload.get("tool") or "")

    try:
        from gates import decide, extract_strings, gated, matches_executor  # 惰性导入

        root = project_root(payload)
        if not gated(tool_name) and not matches_executor(tool_name, root):
            emit({})
            return

        command, file_path, content = extract_strings(payload)
        decision = decide(tool_name, command, file_path, content, root)
    except Exception as exc:  # 自己出 bug 不能把用户锁死
        fail_open(f"{type(exc).__name__}: {exc}")
        return

    if decision is not None:
        emit(block_output(decision), exit_code=0)
    emit({})


if __name__ == "__main__":
    main()
