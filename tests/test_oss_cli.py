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

"""oss_cli 的行为测试：不打网络，全部 stub 掉 HTTP 层。"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "tools"))

import oss_cli  # noqa: E402


def _project(config: dict | None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="oss-cli-"))
    if config is not None:
        (root / ".rtd").mkdir(parents=True)
        (root / ".rtd" / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return root


_FLINK = {"home": "/opt/flink", "sql_client": "/opt/flink/bin/sql-client.sh",
          "rest_endpoint": "http://127.0.0.1:8081"}


def _run(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            code = oss_cli.main(argv)
        except SystemExit as err:  # argparse 的拒绝路径
            code = int(err.code or 0)
    return code, buffer.getvalue()


def test_missing_config_reports_gap_not_crash():
    root = _project(None)
    code, out = _run(["--project", str(root), "flink", "jobs"])
    assert code == 2, out
    assert "[缺口]" in out and "config.json" in out


def test_placeholder_executor_is_treated_as_missing():
    root = _project({"executors": {"oss_flink": {"home": "<Flink 安装目录>", "rest_endpoint": "<地址>"}}})
    code, out = _run(["--project", str(root), "flink", "jobs"])
    assert code == 2, out
    assert "缺字段" in out


def test_flink_jobs_renders_and_json(monkeypatch=None):
    root = _project({"executors": {"oss_flink": _FLINK}})
    calls: list[str] = []

    def fake(url, payload=None, method="GET", timeout=60):
        calls.append(f"{method} {url}")
        return {"jobs": [{"jid": "abc", "state": "FINISHED", "name": "insert-into_sink"}]}

    original = oss_cli.http_json
    oss_cli.http_json = fake
    try:
        code, out = _run(["--project", str(root), "flink", "jobs"])
        assert code == 0, out
        assert "abc" in out and "FINISHED" in out

        code, out = _run(["--project", str(root), "--json", "flink", "jobs"])
        assert json.loads(out)["jobs"][0]["jid"] == "abc"
    finally:
        oss_cli.http_json = original
    assert calls and calls[0].endswith("/jobs/overview")


def test_gateway_run_keeps_last_changelog_value():
    """流模式的 COUNT 是 changelog：终值取最后一条非 UPDATE_BEFORE。"""
    pages = {
        "result/0": {"resultType": "PAYLOAD",
                     "results": {"columns": [{"name": "cnt"}],
                                 "data": [{"kind": "INSERT", "fields": [3]},
                                          {"kind": "UPDATE_BEFORE", "fields": [3]},
                                          {"kind": "UPDATE_AFTER", "fields": [10]}]},
                     "nextResultUri": "/v1/sessions/s/operations/o/result/1"},
        "result/1": {"resultType": "EOS"},
    }

    def fake(url, payload=None, method="GET", timeout=60):
        if method == "DELETE":
            return {}                       # 会话清理
        if url.endswith("/statements"):
            return {"operationHandle": "o"}
        if url.endswith("/status"):
            return {"status": "FINISHED"}
        for key, value in pages.items():
            if url.endswith(key):
                return value
        raise AssertionError(f"未预期的请求：{url}")

    original = oss_cli.http_json
    oss_cli.http_json = fake
    try:
        outcome = oss_cli._gateway_run("http://g:8083", "s", "SELECT COUNT(*) FROM t")
    finally:
        oss_cli.http_json = original
    assert outcome["columns"] == ["cnt"]
    assert outcome["rows"] == [[10]], outcome


def test_evidence_refs_uses_sql_client_by_default():
    """默认通道是 SQL 客户端（Gateway 取结果在 Flink 2.2 上不可靠，实测）。"""
    root = _project({"executors": {"oss_flink": _FLINK,
                                   "oss_paimon": {"connector_jar": "/opt/paimon.jar",
                                                  "catalog_type": "paimon",
                                                  "warehouse": "file:///tmp/wh"}}})
    seen: list[str] = []

    def fake_client(config, sql_text):
        seen.append(sql_text)
        return 0, "+----+-----+\n| cnt |\n+----+-----+\n|  7 |\n+----+-----+"

    original = oss_cli.run_sql_client
    oss_cli.run_sql_client = fake_client
    out_file = root / "refs.json"
    try:
        code, out = _run(["--project", str(root), "evidence", "refs",
                          "--table", "paimon.db_lab.t_orders", "--out", str(out_file)])
    finally:
        oss_cli.run_sql_client = original

    assert code == 0, out
    payload = json.loads(out)
    assert payload["source"] == "flink-sql-client"
    assert payload["tables"][0]["published"] is True
    assert payload["tables"][0]["rows"] == 7
    assert json.loads(out_file.read_text(encoding="utf-8"))["tables"][0]["rows"] == 7
    assert seen and "SELECT COUNT(*) AS cnt FROM paimon.db_lab.t_orders" in seen[0]
    assert "execution.runtime-mode' = 'batch'" in seen[0]


def test_evidence_refs_gateway_channel_still_works():
    root = _project({"executors": {"oss_flink": _FLINK,
                                   "oss_paimon": {"connector_jar": "/opt/paimon.jar",
                                                  "catalog_type": "paimon",
                                                  "warehouse": "file:///tmp/wh"}}})
    seen: list[str] = []

    def fake(url, payload=None, method="GET", timeout=60):
        if method == "DELETE":
            return {}                       # 会话清理
        if url.endswith("/v1/sessions"):
            return {"sessionHandle": "s1"}
        if url.endswith("/statements"):
            seen.append(payload["statement"])
            return {"operationHandle": "o1"}
        if url.endswith("/status"):
            return {"status": "FINISHED"}
        if "/result/0" in url:
            return {"resultType": "PAYLOAD",
                    "results": {"columns": [{"name": "cnt"}], "data": [{"kind": "INSERT", "fields": [7]}]}}
        raise AssertionError(url)

    original = oss_cli.http_json
    oss_cli.http_json = fake
    out_file = root / "refs.json"
    try:
        code, out = _run(["--project", str(root), "evidence", "refs",
                          "--table", "paimon.db_lab.t_orders", "--out", str(out_file),
                          "--via", "gateway"])
    finally:
        oss_cli.http_json = original

    assert code == 0, out
    payload = json.loads(out)
    assert payload["tables"][0]["published"] is True
    assert payload["tables"][0]["rows"] == 7
    assert json.loads(out_file.read_text(encoding="utf-8"))["source"] == "flink-sql-gateway"
    assert any(statement.startswith("CREATE CATALOG") for statement in seen)


def test_read_statements_splits_and_strips_comments():
    path = Path(tempfile.mkdtemp(prefix="oss-sql-")) / "job.sql"
    path.write_text("-- 注释\nSET 'x' = 'y';\nSELECT 1;\n", encoding="utf-8")
    statements = oss_cli.read_statements(str(path))
    assert statements == ["SET 'x' = 'y'", "SELECT 1"], statements


def test_fluss_sql_requires_flux_config():
    root = _project({"executors": {"oss_flink": _FLINK}})
    code, out = _run(["--project", str(root), "fluss", "sql", "-s", "SELECT 1"])
    assert code == 2, out
    assert "oss_fluss" in out


# ---------------------------------------------------------------- 真实输出回归（原样抄自 WSL 实测）

# 成功：客户端把语句 echo 和表格边框粘在一起，所以解析不能按行号硬切
_RAW_OK = """[INFO] Executing SQL from file.

Flink SQL> [INFO] Execute statement succeeded.

Flink SQL> 
> SELECT COUNT(*)+-----+
| cnt |
+-----+
|  10 |
+-----+
1 row in set (296.71 seconds)

Flink SQL> 
Shutting down the session...
done.
"""

# 失败：客户端退出码仍是 0，错误只在输出里
_RAW_FAIL = """Flink SQL> SELECT COUNT(*)[ERROR] Could not execute SQL statement. Reason:
org.apache.calcite.sql.validate.SqlValidatorException: Object 'db_lab' not found within 'paimon'

Shutting down the session...
"""


def test_tableau_count_reads_real_client_output():
    assert oss_cli._tableau_count(_RAW_OK) == 10
    assert oss_cli._tableau_count("没有表格") is None


def test_statement_error_extracted_from_real_client_output():
    assert oss_cli._statement_error(_RAW_OK) == ""
    reason = oss_cli._statement_error(_RAW_FAIL)
    assert "Object 'db_lab' not found within 'paimon'" in reason
    assert "\n" not in reason


def test_count_rows_never_turns_query_failure_into_unpublished():
    """查失败 ≠ 没数据：必须 published=None + error，不能写成 published=False。"""
    config = {"executors": {"oss_flink": _FLINK,
                            "oss_paimon": {"catalog_type": "paimon", "warehouse": "file:///tmp/wh"}}}
    original = oss_cli.run_sql_client
    oss_cli.run_sql_client = lambda _config, _sql: (0, _RAW_FAIL)
    try:
        entry = oss_cli._count_rows(config, "paimon.db_lab.t_orders")
    finally:
        oss_cli.run_sql_client = original
    assert entry["published"] is None, entry
    assert entry["rows"] is None
    assert "db_lab' not found" in entry["error"]


def test_evidence_refs_checks_fluss_table_via_fluss_catalog():
    """fluss.* 表要现建 fluss catalog —— 否则这条 CLI 只覆盖了 Paimon。"""
    root = _project({"executors": {"oss_flink": _FLINK, "oss_fluss": {
        "home": "/opt/fluss", "bootstrap_servers": "localhost:9123"}}})
    seen: list[str] = []

    def fake_client(_config, sql_text):
        seen.append(sql_text)
        return 0, _RAW_OK

    original = oss_cli.run_sql_client
    oss_cli.run_sql_client = fake_client
    try:
        code, out = _run(["--project", str(root), "evidence", "refs",
                          "--table", "fluss.db_lab.log_orders"])
    finally:
        oss_cli.run_sql_client = original
    assert code == 0, out
    assert "CREATE CATALOG IF NOT EXISTS fluss" in seen[0]
    assert "'bootstrap.servers'='localhost:9123'" in seen[0]
    assert json.loads(out)["tables"][0]["rows"] == 10


def test_evidence_refs_reports_each_failing_table_separately():
    root = _project({"executors": {"oss_flink": _FLINK,
                                   "oss_paimon": {"catalog_type": "paimon", "warehouse": "file:///tmp/wh"}}})
    calls: list[str] = []

    def fake_client(_config, sql_text):
        calls.append(sql_text)
        return (0, _RAW_OK) if "t_orders" in sql_text else (0, _RAW_FAIL)

    original = oss_cli.run_sql_client
    oss_cli.run_sql_client = fake_client
    try:
        code, out = _run(["--project", str(root), "evidence", "refs",
                          "--table", "paimon.db_lab.t_orders", "--table", "paimon.db_lab.t_missing"])
    finally:
        oss_cli.run_sql_client = original

    assert code == 2, out                     # 有一张没查成 → 不许报 0
    assert len(calls) == 2, "一张表失败不能掐断其余表"
    tables = json.loads(out)["tables"]
    assert tables[0]["published"] is True and tables[0]["rows"] == 10
    assert tables[1]["published"] is None and tables[1]["error"]


def test_flink_query_uses_client_by_default():
    root = _project({"executors": {"oss_flink": _FLINK}})
    seen: list[str] = []
    original = oss_cli.run_sql_client
    oss_cli.run_sql_client = lambda _config, sql: (seen.append(sql) or (0, _RAW_OK))
    try:
        code, out = _run(["--project", str(root), "flink", "query", "-s", "SELECT 1"])
    finally:
        oss_cli.run_sql_client = original
    assert code == 0, out
    assert seen == ["SELECT 1;\n"]
    assert "1 row in set" in out


def test_sql_client_failure_makes_command_exit_nonzero():
    root = _project({"executors": {"oss_flink": _FLINK}})
    original = oss_cli.run_sql_client
    oss_cli.run_sql_client = lambda _config, _sql: (0, _RAW_FAIL)
    try:
        code, out = _run(["--project", str(root), "flink", "submit", "-f", _write_sql()])
    finally:
        oss_cli.run_sql_client = original
    assert code == 2, out
    assert "db_lab' not found" in out


def _write_sql() -> str:
    path = Path(tempfile.mkdtemp(prefix="oss-cli-sql-")) / "job.sql"
    path.write_text("SELECT COUNT(*) AS cnt FROM paimon.db_lab.t_orders;\n", encoding="utf-8")
    return str(path)


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
    print("oss_cli 测试：全部通过" if not failures else f"oss_cli 测试：{failures} 个失败")
    raise SystemExit(1 if failures else 0)
