"""hook 与宿主的 I/O 约定（Claude Code / Codex 共用）。

* 宿主把一次工具调用的 JSON 写到 stdin；
* 我们把一个 JSON 对象写到 stdout；
* 退出码 0 = 允许（或在 JSON 里给决策），2 = 硬拦。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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


PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
ENGINE_DIR = PLUGIN_ROOT / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


def load_payload() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def trace_payload(event: str, payload: Dict[str, Any]) -> None:
    """把原始 payload 追加到 `$RTD_HOOK_TRACE` 指向的文件（默认关闭）。

    排查宿主差异用：`$env:RTD_HOOK_TRACE="C:\\temp\\rtd-hook.jsonl"` 后跑一次即可看到 payload 形状。
    """
    target = os.environ.get("RTD_HOOK_TRACE", "").strip()
    if not target:
        return
    try:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": event, "payload": payload}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def project_root(payload: Dict[str, Any]) -> Path:
    import core

    cwd = payload.get("cwd")
    start = Path(cwd) if cwd and Path(cwd).is_dir() else Path.cwd()
    return core.find_project_root(start) or start


def emit(obj: Any, exit_code: int = 0) -> None:
    """输出一行 JSON 给宿主。

    故意用 ensure_ascii=True：Windows 控制台默认是 cp936，而宿主按 UTF-8 解析 hook 输出，
    不转义会让中文拦截原因变成乱码（既有插件实测踩过）。
    """
    try:
        sys.stdout.write(json.dumps(obj))
        sys.stdout.flush()
    except Exception:
        pass
    sys.exit(exit_code)


def fail_open(message: str) -> None:
    """hook 自己出 bug 时不能把用户锁死：放行 + 提示。"""
    emit({"systemMessage": f"[realtime-data-plugin] hook 内部错误（fail-open）: {message}"})


def host_command_hint(name: str) -> str:
    """同一动作在两宿主里的写法不同：Codex 是技能名，Claude Code 是斜杠命令。"""
    return f"rtd-{name}" if os.environ.get("PLUGIN_DATA") else f"/{name}"
