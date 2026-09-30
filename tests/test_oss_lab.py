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

"""oss_lab 的行为测试：不装组件、不起进程，runner 与探针全部 stub 掉。"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "tools"))

import oss_lab  # noqa: E402


def _project(config: dict | None, lab: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="oss-lab-"))
    (root / ".rtd").mkdir(parents=True)
    (root / ".rtd" / "config.json").write_text(
        json.dumps(config or {"executors": {}}, ensure_ascii=False), encoding="utf-8"
    )
    if lab is not None:
        (root / ".rtd" / "lab.json").write_text(json.dumps(lab, ensure_ascii=False), encoding="utf-8")
    return root


def _run(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            code = oss_lab.main(argv)
        except SystemExit as err:
            code = int(err.code or 0)
    return code, buffer.getvalue()


KAFKA = {
    "home": "/home/lab/oss/kafka",
    "bootstrap_servers": "127.0.0.1:9092",
}
FLINK = {"home": "/home/lab/oss/flink-2.2.0", "rest_endpoint": "http://127.0.0.1:8081"}


# ---------------------------------------------------------------- 注册表本身


def test_registry_loads_and_ids_are_unique():
    registry = oss_lab.load_registry()
    ids = [item["id"] for item in registry["components"]]
    assert len(ids) == len(set(ids))
    assert "oss_kafka" in ids and "oss_flink" in ids


@pytest.mark.parametrize("component_id", ["oss_flink", "oss_kafka", "oss_paimon", "oss_spark"])
def test_registered_components_declare_their_contract(component_id):
    """tier 1/2 组件必须能被驱动：有 config_ref、required_keys 与合法形态。"""
    registry = oss_lab.load_registry()
    spec = oss_lab.component(registry, component_id)
    assert spec["config_ref"] == f"executors.{spec['id']}"
    assert isinstance(spec["required_keys"], list) and spec["required_keys"]
    assert spec["launch_mode"] in {"service", "library"}
    assert spec["tier"] in {1, 2}


def test_service_components_have_ready_probe_and_library_ones_do_not_pretend():
    registry = oss_lab.load_registry()
    for spec in registry["components"]:
        if spec["launch_mode"] == "service" and spec["tier"] in {1, 2}:
            ready = spec.get("ready") or {}
            assert ready.get("tcp") or ready.get("http") or ready.get("probe_argv"), spec["id"]
        if spec["tier"] == 3:
            assert not spec.get("start"), f"{spec['id']} 是 tier 3，不该有本地启动配方"


# ---------------------------------------------------------------- list / plan


def test_list_marks_unconfigured_and_configured():
    root = _project({"executors": {"oss_kafka": KAFKA}})
    code, out = _run(["--project", str(root), "list", "--json"])
    assert code == 0, out
    rows = {row["id"]: row for row in json.loads(out)["components"]}
    assert rows["oss_kafka"]["configured"] is True
    assert rows["oss_flink"]["configured"] is False
    assert rows["oss_flink"]["missing"] == ["executors.oss_flink 整段未配置"]


def test_placeholder_executor_counts_as_not_configured():
    root = _project({"executors": {"oss_kafka": {"home": "<Kafka 安装目录>",
                                                 "bootstrap_servers": "127.0.0.1:9092"}}})
    code, out = _run(["--project", str(root), "plan", "oss_kafka", "--json"])
    assert code == 0, out
    assert json.loads(out)["gaps"] == ["executors.oss_kafka.home"]


def test_plan_resolves_short_and_qualified_variables():
    root = _project({"executors": {"oss_kafka": KAFKA}})
    code, out = _run(["--project", str(root), "plan", "oss_kafka", "--json"])
    assert code == 0, out
    plan = json.loads(out)
    assert any("/home/lab/oss/kafka/bin/kafka-server-start.sh" in item for item in plan["start"])
    assert "${" not in json.dumps(plan["start"], ensure_ascii=False)


def test_unknown_component_reports_gap_not_traceback():
    root = _project({"executors": {}})
    code, out = _run(["--project", str(root), "plan", "oss_nope"])
    assert code == 2, out
    assert "[缺口]" in out and "oss_kafka" in out


def test_home_prefixed_paths_never_reach_the_shell_as_a_literal_tilde():
    """`~` 的路子有两种错法：被引号裹成字面量、或依赖波浪号展开的解析时机。

    实测出现过落在工作目录下、名字里带 `~` 的目录（安装包被解到那里）。所以统一换成 `$HOME`。
    """
    assert oss_lab._q("~/oss") == '"$HOME"/oss'
    assert oss_lab._q("~/oss/my dir") == '"$HOME"/\'oss/my dir\''
    assert oss_lab._q("~") == '"$HOME"'
    assert oss_lab._q("/abs/path") == "/abs/path"
    assert oss_lab._q("/abs/my path") == "'/abs/my path'"
    for value in ("~/oss/kafka", "~/oss/x.tgz", "~"):
        assert not oss_lab._q(value).startswith("~"), value


# ---------------------------------------------------------------- 一次只起一个


def test_start_refuses_when_another_heavy_component_is_running(monkeypatch):
    root = _project({"executors": {"oss_kafka": KAFKA, "oss_flink": FLINK}})
    (root / ".rtd" / "lab-state.json").write_text(
        json.dumps({"up": "oss_flink", "since": "2026-09-29T20:00:00+08:00"}), encoding="utf-8"
    )
    monkeypatch.setattr(oss_lab, "probe_tcp", lambda target, timeout=2.0: (False, "stub"))
    monkeypatch.setattr(oss_lab, "run_script", lambda ctx, script, timeout=300: (0, "should not run"))
    code, out = _run(["--project", str(root), "start", "oss_kafka"])
    assert code == 4, out
    assert "[拒绝]" in out and "oss_flink" in out


def test_start_stop_others_first_stops_the_running_one(monkeypatch):
    root = _project({"executors": {"oss_kafka": KAFKA, "oss_flink": FLINK}})
    (root / ".rtd" / "lab-state.json").write_text(
        json.dumps({"up": "oss_flink"}), encoding="utf-8"
    )
    executed: list[str] = []

    def fake_run(ctx, script, timeout=300):
        executed.append(script)
        return 0, "ok"

    monkeypatch.setattr(oss_lab, "probe_tcp", lambda target, timeout=2.0: (False, "stub"))
    monkeypatch.setattr(oss_lab, "run_script", fake_run)
    monkeypatch.setattr(oss_lab, "probe", lambda ctx, spec, extra=None, wait=False: (True, ["stub 就绪"]))
    code, out = _run(["--project", str(root), "start", "oss_kafka", "--stop-others"])
    assert code == 0, out
    assert any("stop-cluster.sh" in item for item in executed), executed
    state = json.loads((root / ".rtd" / "lab-state.json").read_text(encoding="utf-8"))
    assert state["up"] == "oss_kafka"


def test_start_reports_gap_when_required_keys_missing(monkeypatch):
    root = _project({"executors": {"oss_kafka": {"home": "/home/lab/oss/kafka"}}})
    monkeypatch.setattr(oss_lab, "run_script", lambda ctx, script, timeout=300: (0, "nope"))
    code, out = _run(["--project", str(root), "start", "oss_kafka"])
    assert code == 2, out
    assert "bootstrap_servers" in out


# ---------------------------------------------------------------- smoke


def test_component_without_a_local_recipe_is_refused_not_faked(tmp_path):
    """没有本地配方的组件必须显式报缺口，不能假装能跑。

    用一份临时注册表构造这种组件。正式注册表里 13 个组件现在都至少有了配方，
    但"配方可以缺、缺了要说清"这条行为本身要一直被测到。
    """
    registry = {
        "lab": {"root_default": "~/oss"},
        "components": [{
            "id": "oss_fake", "display": "Fake", "role": "serving",
            "launch_mode": "service", "tier": 3,
            "config_ref": "executors.oss_fake", "required_keys": [],
        }],
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    root = _project({"executors": {}})
    code, out = _run(["--project", str(root), "--registry", str(reg_path), "smoke", "oss_fake"])
    assert code == 2, out
    assert "没有本地冒烟配方" in out


def test_install_script_has_no_windows_separators(monkeypatch):
    """包内路径是 POSIX 的：用 Path 拼父目录会在 Windows 上得到 `~\\oss` 这种名字。

    实测后果是安装包被解到工作目录下一个带 `~` 的目录里，而目标目录还是空的。
    """
    root = _project({"executors": {}})
    monkeypatch.setattr(oss_lab, "run_script", lambda ctx, script, timeout=300: (0, "ok"))
    code, out = _run(["--project", str(root), "install", "oss_kafka", "--json"])
    assert code == 0, out
    script = json.loads(out)["script"]
    assert "\\" not in script, script
    assert 'mkdir -p "$HOME"/oss' in script, script


def test_smoke_passes_when_expected_lines_come_back(monkeypatch, tmp_path):
    root = _project({"executors": {"oss_kafka": KAFKA}})
    monkeypatch.setattr(oss_lab, "probe_tcp", lambda target, timeout=2.0: (True, "stub"))

    def fake_run(ctx, script, timeout=300):
        if "console-consumer" in script:
            return 0, "1\n2\n3\n"
        return 0, "ok"

    monkeypatch.setattr(oss_lab, "run_script", fake_run)
    code, out = _run(["--project", str(root), "smoke", "oss_kafka",
                      "--count", "3", "--out", str(tmp_path), "--json"])
    assert code == 0, out
    payload = json.loads(out)
    assert payload["passed"] is True
    assert {step["name"] for step in payload["steps"]} == {"topic-create", "produce", "consume-back"}
    assert (tmp_path / "consume-back.txt").is_file()


def test_smoke_fails_when_readback_is_empty(monkeypatch, tmp_path):
    """读回 0 行 = 没数据 = 失败；不能因为退出码是 0 就算通过。"""
    root = _project({"executors": {"oss_kafka": KAFKA}})

    def fake_run(ctx, script, timeout=300):
        return 0, "" if "console-consumer" in script else "ok"

    monkeypatch.setattr(oss_lab, "run_script", fake_run)
    code, out = _run(["--project", str(root), "smoke", "oss_kafka",
                      "--count", "3", "--out", str(tmp_path), "--json"])
    assert code == 3, out
    payload = json.loads(out)
    assert payload["passed"] is False
    failed = [step for step in payload["steps"] if not step["passed"]]
    assert [step["name"] for step in failed] == ["consume-back"]


def test_smoke_counts_only_data_lines_not_the_client_summary(monkeypatch, tmp_path):
    """客户端自己打印的汇总行不算数据：读回 2 条 + 1 行汇总，凑不出 3 条。"""
    root = _project({"executors": {"oss_kafka": KAFKA}})

    def fake_run(ctx, script, timeout=300):
        if "console-consumer" in script:
            return 0, "1\n2\nProcessed a total of 2 messages\n"
        return 0, "ok"

    monkeypatch.setattr(oss_lab, "run_script", fake_run)
    code, out = _run(["--project", str(root), "smoke", "oss_kafka",
                      "--count", "3", "--out", str(tmp_path), "--json"])
    assert code == 3, out
    steps = {step["name"]: step for step in json.loads(out)["steps"]}
    assert steps["consume-back"]["passed"] is False
    assert "预期 ≥ 3 行" in steps["consume-back"]["detail"]


def test_status_marks_library_components_as_not_applicable():
    root = _project({"executors": {}})
    code, out = _run(["--project", str(root), "status", "--json"])
    assert code == 0, out
    rows = {row["id"]: row for row in json.loads(out)["components"]}
    assert rows["oss_paimon"]["running"] is None
    assert "库形态" in rows["oss_paimon"]["detail"][0]
