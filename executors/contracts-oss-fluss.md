# 开源栈执行器契约：Apache Fluss

Fluss 在插件里扮演**流存储**：Flink SQL 通过连接器读写 log 表，也可以作为湖流一体场景的实时层。

## 配置形状

```json
{
  "executors": {
    "oss_fluss": {
      "home": "<Fluss 安装目录>",
      "bootstrap_servers": "<host:port>",
      "connector_jar": "<fluss-flink-<版本>.jar 路径>"
    }
  }
}
```

## 版本对齐（实测的选型依据）

Fluss 的连接器按 Flink 版本分构件，**必须与 Flink 版本对齐**：

| Flink | 连接器构件 |
| --- | --- |
| 2.2 | `fluss-flink-2.2` |
| 2.1 | 只有更早的 0.8.x 系列（实测 Maven 目录） |
| 1.20 | `fluss-flink-1.20`（0.9.x 起） |

版本不一致时的表现是连接器加载失败或运行期报类缺失，**不要**用"换个连接器版本再试"来碰运气：先按上表核对，对不上就如实报告"该组合未验证"。

## 使用契约

| 动作 | 约定 |
| --- | --- |
| 建库建表 | 走 Fluss 客户端；库表名与分区键来自真实查询，不猜 |
| Flink 读写 | catalog 与连接信息全部来自配置；连接器 jar 由使用方放进 Flink `lib/` |
| 证据 | Flink 侧作业终态 + Flink 侧读回的行；Fluss 客户端侧的建表回执 |
| 巡检 | 只读检查连接可用性与读写延迟，不做 compaction 或分区变更 |

## 本地实测结论（2026-09-22，见 docs/oss-lab.md 第十一节）

| 项 | 结论 |
| --- | --- |
| 集群启动 | `bin/local-cluster.sh start` 一次起 zookeeper + coordinator + tablet；ZooKeeper 2181、Fluss 9123 |
| SQL 入口 | **没有 SQL 控制台**——`fluss-console.sh` 是起服务用的；建库建表读写都走 Flink SQL + 连接器 |
| 连接器 | `fluss-flink-2.2-1.0.0.jar` 放进 Flink `lib/` 后重启集群；版本必须与 Flink 对齐（见上面的对齐矩阵） |
| 写入 | 建 catalog / 库 / 日志表（默认 append-only），datagen 流式写入 10 行，作业 `FINISHED`，数据落 `/tmp/fluss-data/db_lab/log_orders-0/log-0` |
| 读回 | 批模式 `COUNT=10`，明细 order_id 1..5 正确 |
| 与 Paimon 的分工 | Fluss 当流存储（日志表、append-only），Paimon 当湖表目录（主键表 + 快照），两者在 Flink SQL 里是两套 catalog，互不替代 |
