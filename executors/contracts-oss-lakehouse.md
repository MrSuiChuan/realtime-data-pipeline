# 开源栈执行器契约：湖表格式（Iceberg / Hudi / Delta）

这三种格式在插件里是**同一类东西**：不是独立服务，而是宿主计算引擎里的一个 catalog 或一组表格式。
注册表里它们都是 `launch_mode = library`、`host_engine` 指向具体的计算引擎，因此共用这一份契约——
再拆三份只是把同一套规则抄三遍，改一处忘两处。

Paimon 有自己的契约（它的主战场是 Flink 侧的流式入湖），不在这份文档里重复。

## 配置形状

```json
{
  "executors": {
    "oss_iceberg": {"runtime_jar": "<iceberg-spark-runtime jar>", "warehouse": "<仓库目录>"},
    "oss_hudi":    {"runtime_jar": "<hudi bundle jar>",        "warehouse": "<仓库目录>"},
    "oss_delta":   {"runtime_jar": "<delta-spark jar>",         "warehouse": "<仓库目录>"}
  }
}
```

判定"已配置"的关键键统一是 `runtime_jar`：**没有 runtime jar 就什么都做不了**，
`warehouse` 可以落到项目侧默认值。占位符不算已配置。

## 三类格式的差异点（必须写进证据，不能含糊）

| 格式 | 建 catalog 的关键配置 | 常见坑 |
| --- | --- | --- |
| Iceberg | `spark.sql.catalog.<名>.type` 与 `...impl` 成对出现 | 少了 impl 会静默退化成普通表 |
| Hudi | 表类型（COW / MOR）与索引策略必须显式声明 | 默认值与预期不一致时，写进去的其实是另一张表 |
| Delta | 需要注册扩展（`spark.sql.extensions`） | 没注册时建表成功、后续读写才报错 |

**结论一律以"批模式读回的行数与明细"为准**：catalog 建出来了、建表语句没报错，都不算写成功。

## 版本对齐（最容易踩的地方）

runtime jar 的构件名里同时编着**宿主引擎大版本**与 **Scala 版本**。两者都对上才加载得起来；
对不上时的表现是运行期类缺失，不是启动就报错——所以不要用"换个 jar 再试"碰运气，
先按发行包实际版本核对构件名，对不上就如实写"该组合未验证"。

## 与数据源流程的关系

湖表的 schema 变更走元表流程的同一套确认纪律：展示对象与影响 → 用户当次确认 → 记录原话。
插件**不管理**各格式自身的后台维护作业（快照过期、compaction、清理），
它们属于数据平台侧，需要时按诊断流程观察，不在这里自动触发。

## 本地实验台

这三项由宿主引擎（Spark / Flink）的实验台配方覆盖：实验台只负责"把引擎起起来 + 带对 jar"，
建表与读写走执行器契约里的通道。**没有真跑过的格式，能力矩阵里就是"未验证"。**
