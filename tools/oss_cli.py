#!/usr/bin/env python3
"""oss_cli —— 面向开源实时栈的薄封装 CLI：一个入口管 Flink 与 Fluss。

    py -3 tools/oss_cli.py flink jobs [--json]
    py -3 tools/oss_cli.py flink status <jobId> [--json]
    py -3 tools/oss_cli.py flink exceptions <jobId>
    py -3 tools/oss_cli.py flink submit -f job.sql
    py -3 tools/oss_cli.py flink query  -s "SELECT COUNT(*) FROM t"
    py -3 tools/oss_cli.py fluss  sql   -f ddl.sql     # Fluss 走 Flink 的 catalog
    py -3 tools/oss_cli.py evidence refs --table paimon.db_lab.t_orders [--out refs.json]

三条设计约束（都是从实测里学来的）：

1. **地址与路径全部来自项目配置** `.rtd/config.json` 的 `executors.oss_flink` / `oss_fluss`；
   缺项就报缺口并停，不猜、不自动装。
2. **作业状态走 REST，SQL 执行走 `--via`**：作业列表/状态/异常用 JobManager REST（原生 JSON）；
   执行 SQL 默认走 SQL 客户端（实测稳），`--via gateway` 用 SQL Gateway REST（结构化，但取结果不稳）。
3. **Fluss 没有独立 SQL 入口**：1.0.0 发行版里 `fluss-console.sh` 只用于起服务，建库建表读写
   都得走 Flink SQL + Fluss 连接器，所以 `fluss sql` 复用的就是 Flink 那条通道（官方另有
   `fluss-gateway` REST 网关，装了可以再加一条直连通道）。

已知的 Gateway 坑（已在本工具里处理）：必须显式配置 `sql-gateway.endpoint.rest.address`；
操作是异步的要先轮询 `/status`；批模式结果页为空、要用流模式 changelog 取终值；
`nextResultUri` 是相对路径。

两条 SQL 通道怎么选（`--via`，默认 client）：

| 通道 | 何时用 | 已知边界 |
| --- | --- | --- |
| `client`（默认） | 真正要"跑出结果"：DDL/DML 执行、取行、取证 | 端到端实测稳；按语句顺序同步执行，**语句本身不结束就不返回** |
| `gateway` | 要结构化 JSON 结果，或想异步提交后就返回 | Flink 2.2 实测取结果页不可靠（流模式 `COUNT` 会把会话打成 ERROR、批模式结果页为空） |
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue


_configure_stdio()


class OssError(Exception):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


# ---------------------------------------------------------------- HTTP 层（测试会替换这两个函数）


def http_json(url: str, payload: dict | None = None, method: str = "GET", timeout: int = 60) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body.strip() else {}


# ---------------------------------------------------------------- 配置


def load_config(explicit: str | None, project: str | None) -> dict:
    if explicit:
        path = Path(explicit)
    else:
        root = Path(project).resolve() if project else Path.cwd()
        candidate = root / ".rtd" / "config.json"
        if not candidate.is_file():
            parent = root
            for _ in range(5):
                parent = parent.parent
                if (parent / ".rtd" / "config.json").is_file():
                    candidate = parent / ".rtd" / "config.json"
                    break
        path = candidate
    if not path.is_file():
        raise OssError(f"找不到配置：{path}", "先跑 /rtd-setup 生成 .rtd/config.json，并填好 executors.oss_*")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise OssError(f"配置不是合法 JSON：{err}") from err


def executor(config: dict, name: str, *required: str) -> dict:
    value = (config.get("executors") or {}).get(name)
    if not isinstance(value, dict):
        raise OssError(f"配置里没有 executors.{name}", "两条路选一条配全；开源路径见 templates/config.example.json")
    # 与引擎同一条规则：<占位符> 不算已配置，否则模板里那句"例如 …"会被当成真地址
    missing = [key for key in required if not _real_value(value.get(key))]
    if missing:
        raise OssError(f"executors.{name} 缺字段：{', '.join(missing)}", "占位符不算已配置")
    return value


def _real_value(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return not (text.startswith("<") and text.endswith(">"))


# ---------------------------------------------------------------- Flink REST


def flink_rest(config: dict) -> str:
    return str(executor(config, "oss_flink", "rest_endpoint")["rest_endpoint"]).rstrip("/")


def gateway_base(config: dict) -> str:
    value = executor(config, "oss_flink", "rest_endpoint")
    return str(value.get("sql_gateway") or value["rest_endpoint"].replace(":8081", ":8083")).rstrip("/")


def cmd_flink_jobs(args) -> int:
    config = load_config(args.config, args.project)
    data = http_json(f"{flink_rest(config)}/jobs/overview")
    jobs = data.get("jobs") or []
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"共 {len(jobs)} 个作业")
        for job in jobs:
            print(f"  {job.get('jid')}  {job.get('state'):<10} {job.get('name')}")
    return 0


def cmd_flink_status(args) -> int:
    config = load_config(args.config, args.project)
    data = http_json(f"{flink_rest(config)}/jobs/{args.job_id}")
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"作业 {data.get('jid')} 状态：{data.get('state')}")
        print(f"  名称：{data.get('name')}")
        print(f"  开始：{data.get('start-time')}  结束：{data.get('end-time')}")
        print(f"  任务：{json.dumps(data.get('tasks') or {}, ensure_ascii=False)}")
    return 0


def cmd_flink_exceptions(args) -> int:
    config = load_config(args.config, args.project)
    data = http_json(f"{flink_rest(config)}/jobs/{args.job_id}/exceptions")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- SQL Gateway


def _gateway_session(base: str) -> str:
    return http_json(f"{base}/v1/sessions", {}, method="POST")["sessionHandle"]


def _gateway_run(base: str, session: str, statement: str, wait_seconds: int = 120) -> dict:
    """执行一条语句；返回 {status, columns, rows}。"""
    handle = http_json(f"{base}/v1/sessions/{session}/statements",
                       {"statement": statement}, method="POST")["operationHandle"]
    status = ""
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        status = str(http_json(f"{base}/v1/sessions/{session}/operations/{handle}/status").get("status") or "")
        if status in {"FINISHED", "ERROR", "CANCELED"}:
            break
        time.sleep(1)
    if status != "FINISHED":
        detail = _fetch_error_detail(f"{base}/v1/sessions/{session}/operations/{handle}/result/0")
        raise OssError(
            f"语句未成功结束：status={status}" + (f"；{detail}" if detail else ""),
            f"语句：{statement[:160]}（失败原因若为空，去 SQL Gateway 日志里看异常）",
        )

    columns: list[str] = []
    rows: list[list[Any]] = []
    uri = f"{base}/v1/sessions/{session}/operations/{handle}/result/0"
    for _ in range(60):
        result = http_json(uri)
        kind = str(result.get("resultType") or "").upper()
        if kind == "EOS":
            break
        if kind != "PAYLOAD":
            break
        payload = result.get("results") or {}
        for column in payload.get("columns") or []:
            name = column.get("name")
            if name and name not in columns:
                columns.append(name)
        for row in payload.get("data") or []:
            values = row.get("fields") if isinstance(row, dict) and "fields" in row else None
            if values is None:
                values = list(row.values()) if isinstance(row, dict) else list(row)
            if isinstance(row, dict) and row.get("kind") == "UPDATE_BEFORE":
                continue          # changelog 的旧值不算结果
            if isinstance(row, dict) and row.get("kind") == "UPDATE_AFTER" and rows:
                # 流模式下聚合查询（如 COUNT）会不断更新同一行：终值覆盖前一版
                rows[-1] = values
                continue
            rows.append(values)
        next_uri = result.get("nextResultUri")
        if not next_uri:
            break
        uri = base + next_uri if str(next_uri).startswith("/") else str(next_uri)
    return {"status": status, "columns": columns, "rows": rows}


def _fetch_error_detail(url: str) -> str:
    """Gateway 失败时状态只有 `ERROR`，真正的原因在结果端点的 500 响应体里（`errors` 字段）。

    实测：语句解析失败时 `/status` 返回 `{"status":"ERROR"}`，而 `/result/0` 回 500 并带上
    完整异常文本。这条把原因捞出来，省得每次去翻日志。
    """
    try:
        http_json(url)
    except urllib.error.HTTPError as err:
        try:
            data = json.loads(err.read().decode("utf-8", "replace"))
            errors = data.get("errors") or []
            if errors:
                return " ".join(str(item) for item in errors)[:400].replace("\n", " ")
        except (ValueError, OSError):
            return ""
    except Exception:
        return ""
    return ""


def _run_gateway(config: dict, statements: list[str], source: str, as_json: bool) -> int:
    base = gateway_base(config)
    session = _gateway_session(base)
    results = []
    try:
        for statement in statements:
            outcome = _gateway_run(base, session, statement)
            results.append({"statement": statement, **outcome})
    finally:
        try:
            http_json(f"{base}/v1/sessions/{session}", method="DELETE")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            pass
    payload = {"source": source, "gateway": base, "results": results}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"· {item['statement'][:90]}")
            print(f"  → {item['status']}；返回 {len(item['rows'])} 行")
            for row in item["rows"][:5]:
                print("     ", row)
    return 0


def _statement_error(raw: str) -> str:
    """从 SQL 客户端输出里抠出语句错误；没错误返回空串。

    退出码不可信——实测客户端在语句失败时仍可能返回 0，错误只落在输出里的
    `[ERROR]` 段。这条是踩出来的：查一张不存在的表时，工具一度把它读成
    "0 行 → 未发布"，等于把"查失败"说成"没数据"。
    """
    index = raw.find("[ERROR]")
    if index < 0:
        return ""
    tail = raw[index + len("[ERROR]"):]
    block = re.split(r"\n\s*\n", tail, maxsplit=1)[0]
    return " ".join(block.split())[:300]


def _run_client(config: dict, statements: list[str], source: str, as_json: bool) -> int:
    sql_text = ";\n".join(statements) + ";\n"
    code, raw = run_sql_client(config, sql_text)
    reason = _statement_error(raw) or (f"SQL 客户端退出码 {code}" if code else "")
    if as_json:
        print(json.dumps({"source": source, "exit_code": code, "statements": statements,
                          "error": reason or None, "raw": raw}, ensure_ascii=False, indent=2))
    else:
        print(raw.strip() or "(SQL 客户端没有输出)")
    if reason:
        print(f"[缺口] SQL 客户端报告错误：{reason}", file=sys.stderr)
        return 2
    return 0


def _execute(args, statements: list[str], source: str) -> int:
    """source 只给通道无关的名字，实际输出里会带上所选通道的后缀。"""
    config = load_config(args.config, args.project)
    if args.via == "gateway":
        return _run_gateway(config, statements, f"{source}-gateway", args.json)
    return _run_client(config, statements, f"{source}-client", args.json)


def cmd_flink_submit(args) -> int:
    return _execute(args, read_statements(args.file), "flink-sql")


def cmd_flink_query(args) -> int:
    return _execute(args, [args.statement], "flink-sql-query")


def cmd_fluss_sql(args) -> int:
    """Fluss 没有独立 SQL 入口，走 Flink 的 catalog —— 所以先校验 oss_fluss 已配置。"""
    config = load_config(args.config, args.project)
    executor(config, "oss_fluss", "home", "bootstrap_servers")
    statements = read_statements(args.file) if args.file else [args.statement]
    return _execute(args, statements, "fluss-via-flink")


def read_statements(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    statements = []
    for chunk in text.split(";"):
        cleaned = "\n".join(line for line in chunk.splitlines() if not line.strip().startswith("--")).strip()
        if cleaned:
            statements.append(cleaned)
    if not statements:
        raise OssError(f"SQL 文件里没有语句：{path}")
    return statements


def run_sql_client(config: dict, sql_text: str) -> tuple[int, str]:
    """调用 Flink SQL 客户端跑一段 SQL，返回（退出码, 原始输出）。

    为什么取证要用它而不是 SQL Gateway：实测 Flink 2.2 的 Gateway 取结果不可靠——
    流模式下 `SELECT COUNT(*)` 的会话自己就从 RUNNING 变 ERROR（Failed to fetchResults），
    批模式下结果页又是空的。而 SQL 客户端这条路是稳的（Paimon 读写就是它跑通的）。
    所以：**提交/状态走 Gateway 与 REST，取数据行走客户端**。测试会替换本函数。
    """
    flink = executor(config, "oss_flink", "home", "sql_client")
    handle, path = tempfile.mkstemp(suffix=".sql", prefix="oss-cli-")
    os.close(handle)
    script = Path(path)
    script.write_text(sql_text, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    if flink.get("java_home"):
        env["JAVA_HOME"] = str(flink["java_home"])
        env["PATH"] = f"{flink['java_home']}/bin{os.pathsep}{env.get('PATH', '')}"
    try:
        proc = subprocess.run(
            [str(flink["sql_client"]), "-f", str(script)],
            cwd=str(flink["home"]), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=600,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError as err:
        raise OssError(f"找不到 SQL 客户端：{flink['sql_client']}", "确认 executors.oss_flink.sql_client 与实际安装一致") from err
    finally:
        script.unlink(missing_ok=True)


def _catalog_statement(config: dict, table: str) -> str:
    """按表名前缀现建对应 catalog。

    SQL 客户端每次 `-f` 都是新会话，catalog 不落盘，所以每条脚本都得自带；
    这同时让 `evidence refs` 既能查 `paimon.*` 也能查 `fluss.*`。
    """
    prefix = table.split(".", 1)[0].lower()
    if prefix == "paimon":
        item = (config.get("executors") or {}).get("oss_paimon") or {}
        if item.get("catalog_type") and item.get("warehouse"):
            return (f"CREATE CATALOG IF NOT EXISTS paimon WITH ('type'='{item['catalog_type']}', "
                    f"'warehouse'='{item['warehouse']}');")
        raise OssError("表在 paimon catalog 里，但配置没给 executors.oss_paimon 的 catalog_type / warehouse")
    if prefix == "fluss":
        item = executor(config, "oss_fluss", "bootstrap_servers")
        return (f"CREATE CATALOG IF NOT EXISTS fluss WITH ('type'='fluss', "
                f"'bootstrap.servers'='{item['bootstrap_servers']}');")
    raise OssError(f"不认识的 catalog 前缀：{prefix}", "目前支持 paimon.* 与 fluss.*")


def _table_preamble(config: dict, table: str) -> list[str]:
    lines = ["SET 'execution.runtime-mode' = 'batch';",
             "SET 'sql-client.execution.result-mode' = 'tableau';"]
    lines.append(_catalog_statement(config, table))
    return lines


def _tableau_count(raw: str, column: str = "cnt") -> int | None:
    """从 tableau 输出里取计数（echo 会粘在边框上，所以不能按行号硬切）：

        +-----+
        | cnt |
        +-----+
        |  10 |
        +-----+
    """
    match = re.search(rf"\|\s*{re.escape(column)}\s*\|[\s\S]{{0,200}}?\|\s*(-?\d+)\s*\|", raw)
    return int(match.group(1)) if match else None


def _count_rows(config: dict, table: str, raw_dir: Path | None = None) -> dict:
    """跑一条 COUNT，把结果整理成 refs_readback 的一条表记录。

    三种结局分得很清：解析不出结果 / 语句失败 → `published: null` 且带 `error`；
    查到 0 行 → `published: false`。**不许把"查失败"写成"没数据"。**
    """
    query = f"SELECT COUNT(*) AS cnt FROM {table};"
    preamble = _table_preamble(config, table)
    sql_text = "\n".join([*preamble, query, ""])
    code, raw = run_sql_client(config, sql_text)
    if raw_dir:
        # 原始输出先落盘再解析：解析挂了也得留下可复核的现场
        (raw_dir / (table.replace(".", "_") + ".sql-client.txt")).write_text(
            raw, encoding="utf-8", newline="\n")
    flink = (config.get("executors") or {}).get("oss_flink") or {}
    command = f"{flink.get('sql_client')} -f <生成的 SQL>   # 内容：{' '.join(preamble)} {query}"
    entry = {"name": table, "query": f"SELECT COUNT(*) AS cnt FROM {table}", "command": command}
    reason = _statement_error(raw) or (f"SQL 客户端退出码 {code}" if code else "")
    if reason:
        return {**entry, "published": None, "rows": None, "error": reason}
    rows = _tableau_count(raw)
    if rows is None:
        return {**entry, "published": None, "rows": None,
                "error": "输出里没解析到 COUNT 结果（客户端结果格式可能变了）"}
    return {**entry, "published": rows > 0, "rows": rows}


# ---------------------------------------------------------------- 证据


def cmd_evidence_refs(args) -> int:
    """把"引用表可读"变成契约 JSON：每张表跑一条真实的 COUNT 查询。

    默认走 **SQL 客户端**（实测稳，也支持 `fluss.*` 表）；`--via gateway` 是备选，
    用来对照 Gateway 的结构化输出。单张表失败不打断其余表：失败的表记
    `published: null` + `error`，退出码 2，**不允许降级成"未发布"**。
    """
    config = load_config(args.config, args.project)
    if args.via == "client":
        raw_dir = Path(args.raw_dir).resolve() if args.raw_dir else None
        if raw_dir:
            raw_dir.mkdir(parents=True, exist_ok=True)
        tables = []
        for table in args.table:
            try:
                tables.append(_count_rows(config, table, raw_dir))
            except OssError as err:
                tables.append({"name": table, "published": None, "rows": None, "error": err.message})
        payload = {
            "observed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "flink-sql-client",
            "tables": tables,
        }
        return _emit_refs(payload, args.out)

    base = gateway_base(config)
    session = _gateway_session(base)
    tables = []
    try:
        for table in args.table:
            query = f"SELECT COUNT(*) AS cnt FROM {table}"
            try:
                # 每条都先建 catalog：会话不落盘，跨表复用要按前缀分别建
                _gateway_run(base, session, _catalog_statement(config, table).rstrip(";"))
                outcome = _gateway_run(base, session, query)
            except OssError as err:
                tables.append({"name": table, "published": None, "rows": None,
                               "query": query, "error": err.message})
                continue
            rows = outcome["rows"][-1][0] if outcome["rows"] else None
            try:
                rows = int(rows) if rows is not None else None
            except (TypeError, ValueError):
                pass
            if rows is None:
                tables.append({"name": table, "published": None, "rows": None, "query": query,
                               "error": "Gateway 结果页为空（Flink 2.2 实测取结果不稳，改用默认的 client 通道）"})
            else:
                tables.append({"name": table, "published": rows > 0, "rows": rows, "query": query})
    finally:
        try:
            http_json(f"{base}/v1/sessions/{session}", method="DELETE")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            pass

    return _emit_refs({
        "observed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "flink-sql-gateway",
        "gateway": base,
        "tables": tables,
    }, args.out)


def _emit_refs(payload: dict, out: str | None) -> int:
    if out:
        Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(item["published"] for item in payload["tables"]) else 2


# ---------------------------------------------------------------- 入口

CHANNEL_HELP = ("SQL 通道：client=SQL 客户端（默认，实测稳，会等语句真正结束）；"
                "gateway=SQL Gateway REST（结构化 JSON，但 Flink 2.2 取结果不稳）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oss_cli", description="开源实时栈薄封装 CLI（Flink / Fluss）")
    parser.add_argument("--config", help=".rtd/config.json 路径")
    parser.add_argument("--project", help="项目根目录（默认从当前目录向上找 .rtd）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    sub = parser.add_subparsers(dest="group", required=True)

    flink = sub.add_parser("flink", help="Flink 执行器")
    flink_sub = flink.add_subparsers(dest="action", required=True)
    flink_sub.add_parser("jobs", help="列出作业").set_defaults(func=cmd_flink_jobs)
    status = flink_sub.add_parser("status", help="单个作业状态")
    status.add_argument("job_id")
    status.set_defaults(func=cmd_flink_status)
    exceptions = flink_sub.add_parser("exceptions", help="作业异常")
    exceptions.add_argument("job_id")
    exceptions.set_defaults(func=cmd_flink_exceptions)
    submit = flink_sub.add_parser("submit", help="提交 SQL 文件")
    submit.add_argument("-f", "--file", required=True)
    submit.add_argument("--via", choices=("client", "gateway"), default="client", help=CHANNEL_HELP)
    submit.set_defaults(func=cmd_flink_submit)
    query = flink_sub.add_parser("query", help="执行一条 SQL 并取回结果")
    query.add_argument("-s", "--statement", required=True)
    query.add_argument("--via", choices=("client", "gateway"), default="client", help=CHANNEL_HELP)
    query.set_defaults(func=cmd_flink_query)

    fluss = sub.add_parser("fluss", help="Fluss（经 Flink 的 catalog 访问）")
    fluss_sub = fluss.add_subparsers(dest="action", required=True)
    fluss_sql = fluss_sub.add_parser("sql", help="执行 Fluss SQL（建库建表读写）")
    fluss_sql.add_argument("-s", "--statement")
    fluss_sql.add_argument("-f", "--file")
    fluss_sql.add_argument("--via", choices=("client", "gateway"), default="client", help=CHANNEL_HELP)
    fluss_sql.set_defaults(func=cmd_fluss_sql)

    evidence = sub.add_parser("evidence", help="产出插件契约证据")
    evidence_sub = evidence.add_subparsers(dest="action", required=True)
    refs = evidence_sub.add_parser("refs", help="引用表回读（refs_readback）")
    refs.add_argument("--table", action="append", required=True, help="可重复：foo.bar.baz")
    refs.add_argument("--out")
    refs.add_argument("--via", choices=("client", "gateway"), default="client",
                      help=CHANNEL_HELP)
    refs.add_argument("--raw-dir", help="client 通道：把每次 SQL 客户端的原始输出写到这个目录")
    refs.set_defaults(func=cmd_evidence_refs)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.group == "fluss" and not (getattr(args, "file", None) or getattr(args, "statement", None)):
        parser.error("fluss sql 需要 -s 或 -f")
    try:
        return args.func(args)
    except OssError as err:
        print(f"[缺口] {err.message}")
        if err.hint:
            print(f"       {err.hint}")
        return 2
    except urllib.error.URLError as err:
        print(f"[连接失败] {err}", file=sys.stderr)
        print("       确认集群与 SQL Gateway 在跑（见 docs/oss-lab.md）", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
