# 第三方依赖与商标边界

开源仓库里最容易含糊的一件事：**到底哪些东西是"本项目"的，哪些是别人的**。这份文件把边界划清楚。

## 一、运行时依赖：零

`engine/`、`hooks/`、`tools/` 与 `evals/` 里的代码**只用 Python 标准库**，不需要 `pip install`。
测试用 pytest（开发期依赖，不随插件分发）。

这条不是洁癖，是刻意的：

* 插件会被装进别人的宿主机里，任何运行时依赖都会变成"装不上"的第一现场；
* 没有依赖，就没有依赖许可与版本漂移的问题，`NOTICE` 也就不需要为它们做声明。

## 二、本仓库包含的第三方内容

| 内容 | 来源 | 许可 |
| --- | --- | --- |
| Apache License 2.0 全文（`LICENSE`） | Apache 软件基金会官方文本 | 文本本身可自由复制 |
| 行为准则 | Contributor Covenant v2.1（CC BY 4.0），已改写 | 署名保留在 `CODE_OF_CONDUCT.md` |

除此之外，仓库内不含任何第三方源码或二进制。`skills/` 是本仓库自己生成的产物。

## 三、实验台会下载的第三方组件（**不进仓库、不随插件分发**）

`tools/oss_lab.py` 会按 `governance/oss-components.json` 的登记，在**使用者自己的机器上**下载并运行
实时组件。这些组件：

* 不随本插件分发，也不出现在任何发布包里；
* 各自适用自己的许可（多数是 Apache-2.0，也有其他许可）；
* 使用者在本地使用它们时，应当遵守各自的许可条款。

登记过的组件与其角色：

| 组件 | 角色 | 形态 |
| --- | --- | --- |
| Apache Flink | 流计算引擎 | 独立服务 |
| Apache Kafka | 消息 / 日志存储 | 独立服务 |
| Apache Spark（Structured Streaming） | 流计算引擎 | 按需提交 |
| Apache Paimon | 湖表目录 | 库（宿主引擎加载） |
| Apache Fluss | 流存储 | 独立服务 |
| Apache Iceberg / Hudi / Delta Lake | 湖表目录 | 库（宿主引擎加载） |
| Apache Pulsar | 消息 / 日志存储 | 独立服务 |
| Apache Doris / StarRocks / ClickHouse | 实时分析 / 服务层 | 独立服务 |
| Debezium | 变更数据捕获 | 插件（跑在 Kafka Connect 上） |
| PostgreSQL | 实验源库（仅 CDC 实验用） | 独立服务 |

## 四、名称与商标

* 本项目的名称与标识归项目所有者所有；
* 上述第三方名称与商标归各自所有者。本仓库提到它们，**只是为了说明兼容对象与实测事实**，
  不表示任何赞助、背书或关联；
* 本仓库不是 Apache 软件基金会的项目，也不声称与之有关联。`GOVERNANCE.md`、
  `docs/apache-readiness-audit.md` 里提到的 "Apache 标准" 指的是**借鉴其通行做法**，
  不是身份声明。

## 五、如果你的分发里带了第三方组件

默认不带。如果你出于方便把它们一起打包分发，责任随之转移：

1. 保留各组件自己的 `LICENSE` 与 `NOTICE`；
2. 在自己的 `NOTICE` 里列出它们；
3. 不要用本项目名称暗示这些组件源自本项目。
