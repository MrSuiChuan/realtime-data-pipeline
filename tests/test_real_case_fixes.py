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

"""真实案例（2026-10-10/11）暴露的问题，修完后的回归用例。

案例：Kafka → Flink → Paimon 做「销售额 Top3」，现场记录见
docs/optimization-real-case-2026-10.md。这里只钉修掉的那几处行为。
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
sys.path.insert(0, str(PLUGIN_ROOT / "tools"))

import core  # noqa: E402
import oss_cli  # noqa: E402
import rtd  # noqa: E402

_FLINK = {"home": "/opt/flink", "rest_endpoint": "http://10.0.0.9:8081",
          "sql_client": "/opt/flink/bin/sql-client.sh"}


def _project(config: dict | None = None) -> Path:
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".rtd").mkdir()
    payload = config if config is not None else {}
    (tmp / ".rtd" / "config.json").write_text(json.dumps(payload, ensure_ascii=False),
                                              encoding="utf-8")
    return tmp


def _run_rtd(*argv: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = rtd.main(list(argv))
    return code, buffer.getvalue()


def _run_cli(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            code = oss_cli.main(argv)
        except SystemExit as exc:      # argparse 用 SystemExit 表达用法错误
            code = int(exc.code or 0)
    return code, buffer.getvalue()


def test_chinese_high_risk_kind_needs_trace() -> None:
    """中文动词也是高风险：`--kind 启动` 结束时必须留追踪 ID。

    案例现场：`--kind publish` 被拦、`--kind 启动` 放行——同一动作两种写法两种结果。
    """
    project = _project()
    _run_rtd("setup", "--project", str(project))
    code, out = _run_rtd("run", "start", "--project", str(project), "--kind", "启动", "--json")
    assert code == 0, out
    run_id = json.loads(out)["run_id"]
    runtime = core.Runtime(project)
    codes = {token for token in core.HIGH_RISK_RUN_TOKENS if not token.isascii()}
    assert {"启动", "发布", "下线"} <= codes, codes
    try:
        runtime.run_finish(run_id, "已验证", "")
    except core.RtError as err:
        assert err.code == "run_trace", err.code
    else:
        raise AssertionError("中文高风险 kind 缺 trace 时应当被拒")
    runtime.run_finish(run_id, "已验证", "flink-job-abc")


def test_status_gives_next_action() -> None:
    """`rtd status` 要说清下一步做什么（案例里阶段/门控对应关系靠读源码才搞清）。"""
    project = _project()
    _run_rtd("setup", "--project", str(project))
    code, out = _run_rtd("status", "--project", str(project), "--json")
    assert code == 0, out
    payload = json.loads(out)
    assert "advance --phase design" in payload["next_action"]

    code, out = _run_rtd("advance", "--project", str(project), "--phase", "design")
    assert code == 0, out
    code, out = _run_rtd("status", "--project", str(project), "--json")
    payload = json.loads(out)
    assert "refs_published" in payload["next_action"] and "evidence add" in payload["next_action"]


def test_flink_cancel_prefers_patch_and_falls_back_to_delete() -> None:
    """Flink 2.2 实测：PATCH ?mode=cancel 可用，DELETE 404——按这个顺序走。"""
    root = _project({"executors": {"oss_flink": _FLINK}})
    calls: list[str] = []

    def patch_ok(url, payload=None, method="GET", timeout=60):
        calls.append(f"{method} {url}")
        if method == "PATCH":
            return {}
        raise AssertionError("PATCH 成功时不该再试 DELETE")

    original = oss_cli.http_json
    oss_cli.http_json = patch_ok
    try:
        code, out = _run_cli(["--project", str(root), "flink", "cancel", "job-1"])
    finally:
        oss_cli.http_json = original
    assert code == 0, out
    assert calls == ["PATCH http://10.0.0.9:8081/jobs/job-1?mode=cancel"], calls

    def patch_404_then_delete(url, payload=None, method="GET", timeout=60):
        calls.append(f"{method} {url}")
        if method == "PATCH":
            raise oss_cli.urllib.error.HTTPError(url, 404, "not found", {}, None)
        return {}

    calls.clear()
    oss_cli.http_json = patch_404_then_delete
    try:
        code, out = _run_cli(["--project", str(root), "flink", "cancel", "job-2"])
    finally:
        oss_cli.http_json = original
    assert code == 0, out
    assert [c.split()[0] for c in calls] == ["PATCH", "DELETE"], calls


def test_slot_timeout_gets_actionable_hint() -> None:
    """批查询撞上"slot 被流作业占满"时，要给出可操作的下一步。"""
    hint = oss_cli._error_hint(
        "java.util.concurrent.TimeoutException: Pending slot request timed out in slot pool")
    assert "slot" in hint and "flink cancel" in hint
    assert oss_cli._error_hint("Table not found") == ""
