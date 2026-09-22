"""引擎行为测试：门控、证据、阶段、执行记录、续跑对账。

只用标准库，`py -3 tests/test_engine.py` 直接可跑（CI 里同样被 pytest 收集）。
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "engine"))

import core  # noqa: E402
import rtd  # noqa: E402

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


def _run(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = rtd.main(list(argv))
    except SystemExit as err:  # argparse 自己的拒绝路径（例如 choices 不匹配）
        code = int(err.code or 0)
    return code, buf.getvalue()


def _project() -> Path:
    return Path(tempfile.mkdtemp(prefix="rtd-test-"))


def _evidence_file(directory: Path, payload: dict, name: str = "raw.json") -> Path:
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_setup_creates_runtime_and_is_idempotent():
    project = _project()
    code, out = _run("setup", "--project", str(project))
    assert code == 0, out
    assert (project / ".rtd" / "_state.json").is_file()
    assert (project / ".rtd" / "config.json").is_file()
    assert (project / ".rtd" / "engine" / "rtd.py").is_file()
    assert ".rtd/" in (project / ".gitignore").read_text(encoding="utf-8")

    code2, out2 = _run("setup", "--project", str(project))
    assert code2 == 0, out2
    assert "新建" not in out2  # 第二次不再重建
    # .gitignore 不重复追加
    assert (project / ".gitignore").read_text(encoding="utf-8").count(".rtd/") == 1


def test_readback_gate_refuses_user_confirm():
    project = _project()
    _run("setup", "--project", str(project))
    code, out = _run(
        "gate", "set", "--project", str(project),
        "--name", "compile_ok", "--user-confirm", "我说过了",
    )
    assert code == 2
    assert "确认不能替代" in out or "回读类" in out


def test_confirm_gate_requires_quote_and_value():
    project = _project()
    _run("setup", "--project", str(project))
    code, _ = _run(
        "gate", "set", "--project", str(project),
        "--name", "debug_confirmed", "--user-confirm", "   ",
    )
    assert code == 2

    code, out = _run(
        "gate", "set", "--project", str(project),
        "--name", "reset_time", "--user-confirm", "就用昨天十点",
    )
    assert code == 2, out
    assert "具体值" in out or "恢复点" in out


def test_evidence_rejects_weak_input():
    project = _project()
    _run("setup", "--project", str(project))
    raw = project / "empty.txt"
    raw.write_text("", encoding="utf-8")
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "compile_receipt", "--from", str(raw), "--tool", "cli", "--command", "compile",
    )
    assert code == 2, out

    bad = _evidence_file(project, {"status": "SUCCESS"})  # 缺 observed_at
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "compile_receipt", "--from", str(bad), "--tool", "cli", "--command", "compile",
    )
    assert code == 2
    assert "observed_at" in out


def test_full_chain_requires_real_evidence():
    project = _project()
    _run("setup", "--project", str(project))

    # 没有证据就设门 → 拒绝
    code, out = _run("gate", "set", "--project", str(project), "--name", "compile_ok", "--evidence", "nope")
    assert code == 2, out

    # 阶段推进：discover 无门 → design
    code, _ = _run("advance", "--project", str(project), "--phase", "design", "--reason", "开始设计")
    assert code == 0

    # design 的门没满足，直接跳到 build → 拒绝
    code, out = _run("advance", "--project", str(project), "--phase", "build", "--reason", "跳过")
    assert code == 2
    assert "refs_published" in out

    # 引用表回读：有一张没发布 → 证据登记成功但校验不通过
    raw = _evidence_file(
        project,
        {"observed_at": "2026-09-21T21:00:00+08:00", "tables": [{"name": "a", "published": True}, {"name": "b", "published": False}]},
    )
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "refs_readback", "--from", str(raw), "--tool", "ops-mcp", "--command", "list_tables --json",
    )
    assert code == 2
    assert "还没发布" in out

    # 补一份全发布的回读 → 通过，设门，推进
    raw = _evidence_file(
        project,
        {"observed_at": "2026-09-21T21:05:00+08:00", "tables": [{"name": "a", "published": True}]},
        name="raw2.json",
    )
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "refs_readback", "--from", str(raw), "--tool", "ops-mcp", "--command", "list_tables --json",
        "--json",
    )
    assert code == 0, out
    evidence_id = json.loads(out)["id"]

    code, _ = _run("gate", "set", "--project", str(project), "--name", "refs_published", "--evidence", evidence_id)
    assert code == 0
    code, _ = _run("advance", "--project", str(project), "--phase", "build", "--reason", "引用已确认")
    assert code == 0

    # build 阶段：编译回执终态不是成功 → 不能开门
    bad_receipt = _evidence_file(project, {"status": "RUNNING", "observed_at": "2026-09-21T21:10:00+08:00"}, name="c1.json")
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "compile_receipt", "--from", str(bad_receipt), "--tool", "cli", "--command", "compile --json", "--json",
    )
    assert code == 2

    good = _evidence_file(project, {"status": "SUCCESS", "observed_at": "2026-09-21T21:12:00+08:00"}, name="c2.json")
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "compile_receipt", "--from", str(good), "--tool", "cli", "--command", "compile --json", "--json",
    )
    assert code == 0, out
    compile_id = json.loads(out)["id"]
    code, _ = _run("gate", "set", "--project", str(project), "--name", "compile_ok", "--evidence", compile_id)
    assert code == 0
    code, _ = _run("advance", "--project", str(project), "--phase", "debug", "--reason", "编译通过")
    assert code == 0

    # 状态可读
    code, out = _run("status", "--project", str(project), "--json")
    payload = json.loads(out)
    assert payload["phase"] == "debug"
    assert payload["gates_satisfied"] == ["compile_ok", "refs_published"]


def test_verify_detects_tampered_evidence():
    project = _project()
    _run("setup", "--project", str(project))
    raw = _evidence_file(project, {"status": "SUCCESS", "observed_at": "2026-09-21T21:12:00+08:00"})
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "compile_receipt", "--from", str(raw), "--tool", "cli", "--command", "compile --json", "--json",
    )
    assert code == 0
    evidence_id = json.loads(out)["id"]

    stored = project / ".rtd" / "_evidence" / f"{evidence_id}.json"
    stored.write_text(json.dumps({"status": "SUCCESS", "observed_at": "改过了"}), encoding="utf-8")

    code, out = _run("verify", "--project", str(project))
    assert code == 2
    assert "哈希" in out or "改动" in out


def test_run_records_only_enum_statuses():
    project = _project()
    _run("setup", "--project", str(project))
    code, out = _run("run", "start", "--project", str(project), "--kind", "publish", "--summary", "发布任务", "--json")
    assert code == 0, out
    run_id = json.loads(out)["run_id"]

    # 状态词不在枚举里：命令行层拦一次，引擎层再拦一次（两层都要拦）
    code, _ = _run("run", "finish", "--project", str(project), "--run", run_id, "--status", "搞定了")
    assert code == 2
    runtime = core.Runtime(project)
    try:
        runtime.run_finish(run_id, "搞定了", "")
    except core.RtError as err:
        assert err.code == "run_status"
    else:
        raise AssertionError("非枚举状态词应当被引擎拒绝")

    code, _ = _run("run", "finish", "--project", str(project), "--run", run_id, "--status", "已受理", "--trace", "tr-1")
    assert code == 0
    assert runtime.latest_runs()[-1]["status"] == "已受理"


def test_resume_reports_mismatch_without_overwriting():
    project = _project()
    _run("setup", "--project", str(project))
    _run("object", "set", "--project", str(project), "--file-id", "F-1", "--name", "job_a")

    code, out = _run("resume", "--project", str(project), "--observed", json.dumps({"file_id": "F-2"}))
    assert code == 2
    assert "不一致" in out or "对账失败" in out

    code, out = _run("resume", "--project", str(project), "--observed", json.dumps({"file_id": "F-1"}))
    assert code == 0, out


def test_env_check_lists_gaps_for_empty_config():
    project = _project()
    _run("setup", "--project", str(project))
    (project / ".rtd" / "config.json").write_text(json.dumps({"executors": {}, "limits": {}}), encoding="utf-8")
    code, out = _run("env", "check", "--project", str(project), "--json")
    assert code == 0
    payload = json.loads(out)
    assert payload["ready"] is False
    assert any("mcp_ops" in gap for gap in payload["gaps"])
    assert payload["limits"]["scan_budget_s"] == 120


def test_placeholder_config_is_not_ready():
    """刚跑完 setup 时配置里全是占位符，不能报"齐了"。"""
    project = _project()
    _run("setup", "--project", str(project))
    code, out = _run("env", "check", "--project", str(project), "--json")
    assert code == 0
    payload = json.loads(out)
    assert payload["ready"] is False
    assert any("executors.cli 未配置" == gap for gap in payload["gaps"])


def test_evidence_expires_when_object_version_changes():
    """RTD-016：对象换版本后，旧证据设门必须被拒（原先这条判断是死代码）。"""
    project = _project()
    _run("setup", "--project", str(project))
    _run("object", "set", "--project", str(project), "--file-id", "F-1", "--version", "v1")
    raw = _evidence_file(project, {"status": "SUCCESS", "observed_at": "2026-09-21T22:00:00+08:00"}, "c-v1.json")
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "compile_receipt", "--from", str(raw), "--tool", "cli", "--command", "compile --json", "--json",
    )
    assert code == 0, out
    evidence_id = json.loads(out)["id"]
    assert json.loads(out)["object_version"] == "v1"

    # 同版本：可以设门
    code, out = _run("gate", "set", "--project", str(project), "--name", "compile_ok", "--evidence", evidence_id)
    assert code == 0, out

    # 对象换版本后，同一份证据拿去设另一个门 → 拒
    _run("object", "set", "--project", str(project), "--version", "v2")
    state = core.Runtime(project).load_state()
    state["gates"].pop("compile_ok", None)
    core.Runtime(project).save_state(state)
    code, out = _run("gate", "set", "--project", str(project), "--name", "compile_ok", "--evidence", evidence_id)
    assert code == 2, out
    assert "过期" in out


def test_high_risk_run_requires_trace_id():
    """RTD-017：启停/发布类执行记录结束时必须留追踪 ID。"""
    project = _project()
    _run("setup", "--project", str(project))

    code, out = _run("run", "start", "--project", str(project), "--kind", "lifecycle-start", "--summary", "启动", "--json")
    assert code == 0, out
    run_id = json.loads(out)["run_id"]
    code, out = _run("run", "finish", "--project", str(project), "--run", run_id, "--status", "已受理")
    assert code == 2, out
    assert "追踪 ID" in out
    code, out = _run(
        "run", "finish", "--project", str(project), "--run", run_id,
        "--status", "已受理", "--trace", "trace-123",
    )
    assert code == 0, out

    # 只读类不强制
    code, out = _run("run", "start", "--project", str(project), "--kind", "inspect", "--summary", "巡检", "--json")
    read_run = json.loads(out)["run_id"]
    code, out = _run("run", "finish", "--project", str(project), "--run", read_run, "--status", "已验证")
    assert code == 0, out


def test_evidence_expires_when_object_identity_changes():
    """RTD-025：换了对象（文件级 ID 变了）旧证据同样作废，不能只看版本号。"""
    project = _project()
    _run("setup", "--project", str(project))
    _run("object", "set", "--project", str(project), "--file-id", "F-1", "--version", "v1")
    raw = _evidence_file(project, {"status": "SUCCESS", "observed_at": "2026-09-21T23:00:00+08:00"}, "c-f1.json")
    code, out = _run(
        "evidence", "add", "--project", str(project),
        "--kind", "compile_receipt", "--from", str(raw), "--tool", "cli", "--command", "compile --json", "--json",
    )
    assert code == 0, out
    evidence_id = json.loads(out)["id"]
    assert json.loads(out)["object_file_id"] == "F-1"

    # 换成另一个对象：版本一样，但证据必须失效
    _run("object", "set", "--project", str(project), "--file-id", "F-2", "--version", "v1")
    code, out = _run("gate", "set", "--project", str(project), "--name", "compile_ok", "--evidence", evidence_id)
    assert code == 2, out
    assert "过期" in out


def test_non_sequential_advance_requires_reason():
    """RTD-026：回跳/跳阶段必须写理由，空理由等于没留痕。"""
    project = _project()
    _run("setup", "--project", str(project))
    runtime = core.Runtime(project)

    # 跳阶段（discover → publish）：允许但要理由
    state = runtime.load_state()
    try:
        runtime.advance(state, "publish", "", allow_back=True)
    except core.RtError as err:
        assert err.code == "phase_reason", err.code
    else:
        raise AssertionError("空理由的跳阶段应当被拒")

    move = runtime.advance(state, "publish", "手工补录历史阶段：本地调试环境重建", allow_back=True)
    assert move == {"from": "discover", "to": "publish"}

    # 回跳（publish → build）：同样要理由
    runtime.save_state(state)
    state = runtime.load_state()
    try:
        runtime.advance(state, "build", "", allow_back=True)
    except core.RtError as err:
        assert err.code == "phase_reason", err.code
    else:
        raise AssertionError("空理由的回跳应当被拒")

    # 回跳是"重做更早的阶段"，不该拿那个阶段的出口门来卡自己：有理由即放行
    code, out = _run("advance", "--project", str(project), "--phase", "build", "--allow-back",
                     "--reason", "回跳补编译证据")
    assert code == 0, out
    assert core.Runtime(project).load_state()["phase"] == "build"


def test_setup_records_plugin_version():
    """RTD-027：运行时里要能看出这份状态是哪版插件产生的。"""
    project = _project()
    _run("setup", "--project", str(project))
    state = core.Runtime(project).load_state()
    assert state["engine"]["hash"]
    assert state["engine"]["plugin_version"]


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
    print("引擎测试：全部通过" if not failures else f"引擎测试：{failures} 个失败")
    raise SystemExit(1 if failures else 0)
