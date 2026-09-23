# 开源栈执行器契约：Apache Flink

把 Flink 当"执行器"用时，插件只依赖两类稳定接口：**SQL 客户端提交**与**REST 只读查询**。这两条都不写死路径，全部从 `.rtd/config.json` 的 `executors.oss_flink` 读。

## 配置形状

```json
{
  "executors": {
    "oss_flink": {
      "home": "<Flink 安装目录>",
      "sql_client": "<home>/bin/sql-client.sh",
      "rest_endpoint": "http://127.0.0.1:8081",
      "java_home": "<JDK 路径>"
    }
  }
}
```

缺 `home` 或 `rest_endpoint` 就报缺口并停，不猜路径、不自动装。

## 两条接口的分工（重要）

| 用途 | 用哪个 | 为什么 |
| --- | --- | --- |
| 提交作业、建表、跑 DDL/DML | SQL 客户端（`-f <file>`） | 提交是动作，输出是给人看的表格 |
| 取证据（作业状态、Job ID、异常） | REST 接口 | **返回结构化 JSON**，能直接进证据账本 |

这条分工不是洁癖：`rtd.py evidence add` 只收结构化证据，而 SQL 客户端的输出是文本表格，拿去当证据会被拒（见 `docs/oss-lab.md` 第四节第 3 条）。

## 提交与轮询约定

1. 非交互模式（`-f`）下**必须**在脚本里显式设置结果模式，否则客户端直接报错拒绝执行查询；
2. 提交后从输出里取 Job ID，再用 REST 查 `state`；`state` 为 `FINISHED`/`FAILED`/`CANCELED` 才算终态；
3. 作业状态是**平台回读**，可作 `publish_ok` 一类的证据；SQL 客户端自己打印的"提交成功"只是受理，不算生效。

## 已知缺口（实测）

| 缺口 | 事实 | 处置 |
| --- | --- | --- |
| 集群会话依赖 | `start-cluster.sh` 在 WSL 里会随会话结束收到 SIGHUP 被杀 | 在长驻会话或容器里起集群；报告里写清这一点 |
| 任务槽就绪有延迟 | 集群脚本返回后 TaskManager 尚未注册完 | 查 `/overview` 前先等几秒，别急着判"起不来" |
| 时区 | SQL 会话默认 UTC，与机器本地时区不一致 | 验证时间语义前先确认会话时区 |

## 巡检与诊断怎么用它

只读来源：REST 的 `/jobs/overview`、`/jobs/<id>`、`/jobs/<id>/exceptions`，加上 TaskManager 的 `.out`/`.log`。**不启动、不停止、不取消作业**——要变更走 `runbook-lifecycle.md` 的门。

## 结构化取证：SQL Gateway REST（本地实测）

插件要求证据是 JSON。三条通道的分工（**2026-09-23 全部在本地实测过**）：

| 通道 | 形态 | 实测结论 |
| --- | --- | --- |
| REST `/jobs/*` | 原生 JSON | 可取作业状态与异常，适合"作业终态"类证据 |
| SQL Gateway `/v1/sessions` | 原生 JSON 查询结果 | 能跑通，但**取结果页不可靠**：必须显式配置 `sql-gateway.endpoint.rest.address`、操作要先轮询 `/status`、批模式结果页为空、流模式的 `COUNT` 会把会话自己打成 ERROR |
| SQL 客户端 + 解析输出 | 文本表格解析成契约 JSON | **默认取证通道**：跑通 `paimon.*` 与 `fluss.*` 两张表，行数与真实值一致；原始输出必须留档 |

**判据不放松**：查失败（表不存在、语法错）不能写成"0 行 / 未发布"。客户端在语句失败时**退出码仍可能是 0**，错误只在输出的 `[ERROR]` 段里，所以成败按文本判定：解析不出结果或出现 `[ERROR]` 一律记 `published: null` + `error`，退出码 2。

## 薄封装 CLI（`tools/oss_cli.py`）

把上面这些接口包成一条命令，避免每次手拼 REST 路径与 SQL 脚本。配置全部来自 `.rtd/config.json` 的 `executors.oss_flink`（`rest_endpoint` 必填；`home` / `sql_client` 供客户端通道用）。

| 子命令 | 做什么 | 走哪条通道 |
| --- | --- | --- |
| `flink jobs` | 列作业与状态（`/jobs/overview`） | REST |
| `flink status <jobId>` / `flink exceptions <jobId>` | 单作业状态与异常 | REST |
| `flink submit -f <sql 文件>` | 提交 DDL/DML | `--via`（默认 `client`） |
| `flink query -s "<SQL>"` | 跑一条语句并取回结果 | `--via`（默认 `client`） |
| `evidence refs --table <catalog.db.table>` | 每张表跑一条真实 `COUNT`，产出 `refs_readback` 契约 JSON | `--via`（默认 `client`，`--raw-dir` 留档原始输出） |

三处必须知道的行为：

1. **`--via client`（默认）会等语句真正结束**：提交一个不结束的流作业就会一直等。要异步提交就显式用 `--via gateway`，并接受它的取结果限制。
2. **CLI 必须跑在能连到集群的那台机器上**：`rest_endpoint` 是集群侧地址，跨机器/跨 WSL 边界能不能连通由使用者自己核实（本地实测是"在 WSL 里跑"）。
3. **catalog 现建**：`evidence refs` 按表名前缀（`paimon.` / `fluss.`）在每条脚本里 `CREATE CATALOG IF NOT EXISTS`——SQL 客户端每次 `-f` 都是新会话，catalog 不落盘。

实测记录（命令、原始输出、失败案例）在 `docs/oss-lab.md` 第十二节。
