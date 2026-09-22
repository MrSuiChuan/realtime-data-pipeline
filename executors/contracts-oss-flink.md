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
