"""hook 判定逻辑测试：三条规则各自的正例与负例。

判定是纯函数（`hooks/gates.decide`），所以不需要模拟宿主就能测。
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

import gates  # noqa: E402


def _project(cli_name: str = "myplatformcli", with_confirm: bool = False) -> Path:
    root = Path(tempfile.mkdtemp(prefix="rtd-hook-"))
    runtime = root / ".rtd"
    (runtime / "_records").mkdir(parents=True, exist_ok=True)
    (runtime / "config.json").write_text(
        json.dumps({"executors": {"cli": {"cmd": cli_name}}}), encoding="utf-8"
    )
    if with_confirm:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        (runtime / "_records" / "gates.jsonl").write_text(
            json.dumps({"at": stamp, "gate": "start_confirmed", "action": "set", "source": "user_confirm", "quote": "开始吧"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    return root


def test_evidence_write_is_blocked():
    root = _project()
    decision = gates.decide("bash", "echo '{}' > .rtd/_evidence/compile_receipt-1.json", "", "", root)
    assert decision is not None and decision.gate == "evidence_write"

    decision = gates.decide("apply_patch", "", str(root / ".rtd" / "_state.json"), "{}", root)
    assert decision is not None and decision.gate == "evidence_write"


def test_yes_flag_needs_recent_confirmation():
    root = _project()
    decision = gates.decide("bash", "myplatformcli publish --publish --yes", "", "", root)
    assert decision is not None
    assert decision.gate in {"yes_flag", "high_risk"}

    ok_root = _project(with_confirm=True)
    assert gates.decide("bash", "myplatformcli publish --yes", "", "", ok_root) is None


def test_high_risk_verb_needs_confirmation():
    root = _project()
    decision = gates.decide("bash", "myplatformcli deploy --start --reset-time 2026-09-20 10:00:00", "", "", root)
    assert decision is not None and decision.gate == "high_risk"

    ok_root = _project(with_confirm=True)
    assert gates.decide("bash", "myplatformcli deploy --start", "", "", ok_root) is None


def test_ordinary_commands_pass():
    root = _project()
    assert gates.decide("bash", "git status", "", "", root) is None
    assert gates.decide("bash", "myplatformcli search --name job_a", "", "", root) is None


def test_stale_confirmation_does_not_count():
    root = _project()
    old = datetime.now().astimezone() - timedelta(hours=3)
    (root / ".rtd" / "_records" / "gates.jsonl").write_text(
        json.dumps({"at": old.isoformat(timespec="seconds"), "source": "user_confirm", "gate": "start_confirmed"}) + "\n",
        encoding="utf-8",
    )
    decision = gates.decide("bash", "myplatformcli deploy --start", "", "", root)
    assert decision is not None and decision.gate == "high_risk"


def test_confirm_window_and_read_lines_come_from_config():
    """RTD-021：窗口与读取行数必须能从 .rtd/config.json 覆盖，不再硬编码。"""
    root = _project()
    stamp = (datetime.now().astimezone() - timedelta(minutes=5)).isoformat(timespec="seconds")
    (root / ".rtd" / "_records" / "gates.jsonl").write_text(
        json.dumps({"at": stamp, "source": "user_confirm", "gate": "start_confirmed"}) + "\n",
        encoding="utf-8",
    )
    # 默认 30 分钟窗口：5 分钟前的确认有效
    assert gates.decide("bash", "myplatformcli deploy --start", "", "", root) is None

    # 窗口收到 1 分钟：同一条确认立刻失效
    (root / ".rtd" / "config.json").write_text(
        json.dumps({"executors": {"cli": {"cmd": "myplatformcli"}}, "limits": {"confirm_window_minutes": 1}}),
        encoding="utf-8",
    )
    decision = gates.decide("bash", "myplatformcli deploy --start", "", "", root)
    assert decision is not None and decision.gate == "high_risk"


def test_record_read_lines_limits_how_far_back_confirmations_are_seen():
    root = _project()
    now_stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [json.dumps({"at": now_stamp, "source": "user_confirm", "gate": "start_confirmed"})]
    lines += [json.dumps({"at": now_stamp, "source": "platform_readback"}) for _ in range(10)]
    (root / ".rtd" / "_records" / "gates.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 只看最后 5 行时，那条确认读不到
    (root / ".rtd" / "config.json").write_text(
        json.dumps({"executors": {"cli": {"cmd": "myplatformcli"}}, "limits": {"record_read_lines": 5}}),
        encoding="utf-8",
    )
    assert gates.decide("bash", "myplatformcli deploy --start", "", "", root) is not None
    # 放开读取行数就恢复
    (root / ".rtd" / "config.json").write_text(
        json.dumps({"executors": {"cli": {"cmd": "myplatformcli"}}, "limits": {"record_read_lines": 50}}),
        encoding="utf-8",
    )
    assert gates.decide("bash", "myplatformcli deploy --start", "", "", root) is None


def test_gated_tool_names():
    assert gates.gated("apply_patch") is True
    assert gates.gated("exec_command") is True
    assert gates.gated("write") is True
    assert gates.gated("read_file") is False
    assert gates.gated("web_search") is False


def test_engine_side_mcp_write_is_blocked():
    """RTD-018：引擎侧 MCP 出现启停动词一律拒绝，不看有没有确认。"""
    root = _project()
    (root / ".rtd" / "config.json").write_text(
        json.dumps({"executors": {"mcp_engine": "engine-mcp", "mcp_ops": "ops-mcp"}}), encoding="utf-8"
    )
    decision = gates.decide("mcp__engine-mcp__restartJob", "", "", "", root)
    assert decision is not None and decision.gate == "engine_readonly"

    # 只读查询放行
    assert gates.decide("mcp__engine-mcp__queryExceptions", "", "", "", root) is None


def test_platform_mcp_write_needs_confirmation():
    root = _project()
    (root / ".rtd" / "config.json").write_text(
        json.dumps({"executors": {"mcp_ops": "ops-mcp"}}), encoding="utf-8"
    )
    assert gates.matches_executor("mcp__ops-mcp__deployPlan", root) is True

    decision = gates.decide("mcp__ops-mcp__deployPlan", "", "", "", root)
    assert decision is not None and decision.gate == "mcp_high_risk"

    ok_root = _project(with_confirm=True)
    (ok_root / ".rtd" / "config.json").write_text(
        json.dumps({"executors": {"mcp_ops": "ops-mcp"}}), encoding="utf-8"
    )
    assert gates.decide("mcp__ops-mcp__deployPlan", "", "", "", ok_root) is None
    assert gates.decide("mcp__ops-mcp__listTasks", "", "", "", ok_root) is None


def test_extract_strings_handles_both_host_shapes():
    claude_shape = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
    assert gates.extract_strings(claude_shape)[0] == "ls -la"

    codex_shape = {"tool": "exec_command", "command": "py -3 rtd.py status", "cwd": "/tmp"}
    assert gates.extract_strings(codex_shape)[0] == "py -3 rtd.py status"

    patch_shape = {"tool_name": "apply_patch", "tool_input": {"file_path": "a/b.py", "content": "print(1)"}}
    command, file_path, content = gates.extract_strings(patch_shape)
    assert command == "" and file_path == "a/b.py" and content == "print(1)"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"[ OK ] {name}")
        except AssertionError as err:
            failures += 1
            print(f"[FAIL] {name}: {err}")
    print()
    print("hook 测试：全部通过" if not failures else f"hook 测试：{failures} 个失败")
    raise SystemExit(1 if failures else 0)
