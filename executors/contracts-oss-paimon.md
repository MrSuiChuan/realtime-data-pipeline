# 开源栈执行器契约：Apache Paimon

Paimon 在插件里扮演**湖表目录**：Flink SQL 里以 catalog 形态出现，提供主键表、分区表与快照语义。

## 配置形状

```json
{
  "executors": {
    "oss_paimon": {
      "connector_jar": "<paimon-flink-<版本>.jar 路径>",
      "catalog_type": "paimon",
      "warehouse": "file:///tmp/paimon-warehouse"
    }
  }
}
```

## 使用契约

| 动作 | 约定 |
| --- | --- |
| 建 catalog | 由 Flink SQL 客户端执行；`warehouse` 必须来自配置，不写死在脚本里 |
| 建表 | 主键表必须显式声明 `PRIMARY KEY ... NOT ENFORCED`；分区表用 `PARTITIONED BY` |
| 流式写入 | 必须开检查点（否则数据不落盘、读不回来）；间隔走项目配置 `limits` |
| 读回验证 | 用批模式查询，**不要**用流模式读同一张表来"证明写成功" |
| 证据 | 行数与明细查回来的结果 + 作业终态；两者都要留 |

## 已知前置条件（实测踩过）

**Paimon 的 filesystem catalog 依赖 Hadoop FileSystem API**，而 Flink 2.x 发行包不再自带 shaded Hadoop。缺依赖时的报错是：

```
java.lang.ClassNotFoundException: org.apache.hadoop.conf.Configuration
```

处置：把 `flink-shaded-hadoop-2-uber`（或等价的 hadoop-common 依赖集）放进 Flink 的 `lib/`，再重启集群。这条被记进 `governance/capability-matrix.json` 的已知缺口，并在 `docs/oss-lab.md` 留了复现过程。

## 边界

- 插件**不管理** Paimon 的 compaction、快照过期等表维护作业；它们属于数据平台侧，需要时按诊断流程观察，不在这里自动触发；
- Paimon 表的 schema 变更走元表流程（`runbook-metatable.md`）的同一套确认纪律。

## 本地实测结论（2026-09-22，见 docs/oss-lab.md）

| 项 | 结论 |
| --- | --- |
| 前置依赖 | 必须在 Flink `lib/` 放 `flink-shaded-hadoop-2-uber`；补齐后 `ClassNotFoundException` 消失 |
| 流式写入 | 开 3 秒检查点的 datagen→Paimon 写入，作业 `FINISHED`，warehouse 出 `snapshot/manifest/parquet` |
| 读回 | 批模式 `COUNT=10`，明细行正确 |
| `refs_readback` 的等价口径 | OSS 场景没有"已发布版本"这个概念，**等价物是"表存在、可读、查询能返回行"**——用一条真实的 COUNT 查询证明（`published = rows > 0`），不靠声明 |
