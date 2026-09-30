# 开源实时组件台账

这是**组件维度**的台账：装了哪些组件、各自扮演什么角色、本机真跑到了哪一步、还差什么。
工作项维度的台账在 `work-ledger.yaml`（AWR 的权威源），两者不重复：那份记"谁在什么时候做了什么"，
这份记"每个组件现在是什么状态"。

维护方式只有一条：**先改 `governance/oss-components.json`，再跑 `tools/validate_plugin.py`**。
本文件是那份注册表与实测记录的汇总，不另立一份组件清单——两份清单必然漂移。

## 一、登记总表

「层」是注册表里的 tier：1 = 已在本机真跑过，2 = 已登记且构件可获取但还没跑通，3 = 只登记角色与配置形状。

| 组件 | 角色 | 形态 | 层 | 构件就绪判定键 | 本机真跑 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| Apache Flink | 流计算引擎 | service | 1 | `home` / `rest_endpoint` | 是（2026-09-22） | `docs/oss-lab.md` 三、十二节 |
| Apache Paimon | 湖表目录 | library | 1 | `connector_jar` / `warehouse` | 是（2026-09-22，Flink 侧） | `docs/oss-lab.md` 八节 |
| Apache Fluss | 流存储 | service | 1 | `home` / `bootstrap_servers` | 是（2026-09-22） | `docs/oss-lab.md` 十一节 |
| Apache Kafka | 消息 / 日志存储 | service | 1 | `home` / `bootstrap_servers` | 是（2026-09-29） | `docs/oss-lab.md` 十三节 |
| Apache Spark（Structured Streaming） | 流计算引擎 | service | 1 | `home` | 是（2026-09-29） | `docs/oss-lab.md` 十四节 1 |
| Apache Iceberg | 湖表目录 | library | 1 | `runtime_jar` | 是（2026-09-29） | `docs/oss-lab.md` 十四节 2 |
| Apache Hudi | 湖表目录 | library | 1 | `runtime_jar` | 是（2026-09-29） | `docs/oss-lab.md` 十四节 2 |
| Delta Lake | 湖表目录 | library | 1 | `packages` / `warehouse` | 是（2026-09-29） | `docs/oss-lab.md` 十四节 2 |
| ClickHouse | 实时分析 / 服务层 | service | 1 | `home` / `tcp_endpoint` | 是（2026-09-29） | `docs/oss-lab.md` 十四节 3 |
| Debezium | 变更数据捕获 | service | 1 | `home` / `plugin_dir` / `connect_url` | 是（2026-09-29） | `docs/oss-lab.md` 十四节 4 |
| Apache Pulsar | 消息 / 日志存储 | service | 1 | `home` / `service_url` | 是（2026-09-30） | `docs/oss-lab.md` 十五节 |
| Apache Doris | 实时分析 / 服务层 | service | 3 | — | **否：构件来源没找到** | `docs/oss-lab.md` 十四节 5 |
| StarRocks | 实时分析 / 服务层 | service | 1 | `fe_image` / `be_image` / `mysql_endpoint` | 是（2026-09-30） | `docs/oss-lab.md` 十七节 |

「未验证」是状态，不是语气：它表示**没有可复核的原始输出**。tier 3 的组件连本地配方都没有，
所以既不进"两条路选一条配全"的判定，也不会被 `rtd-env` 当成缺口报出来——注册表里写了理由。

## 二、逐个组件的现状与下一步

### Flink（compute，已真跑）

批作业出结果、流作业提交到 REST 可查的 Job ID、SQL Gateway 可作为备选取证通道。
已知缺口：集群随会话收到 SIGHUP 被杀；非交互模式必须显式设结果模式；SQL 会话默认 UTC。

下一步：把它与消息队列连起来跑一条真正端到端的流链路（依赖 Kafka 那一项先落地）。

### Paimon（lake，已真跑，Flink 宿主）

建 catalog、主键分区表、流式写入 10 行、批模式读回 COUNT=10、warehouse 落盘齐全。
已知缺口：filesystem catalog 需要把 shaded Hadoop 依赖放进 Flink `lib/`；流式写入必须开检查点。

### Fluss（stream_storage，已真跑）

本地集群一次起三件；Flink SQL 建 catalog / 库 / 日志表并流式写入 10 行；批模式读回 COUNT=10。
已知缺口：发行版没有 SQL 控制台；连接器构件按 Flink 版本分发必须对齐；直连官方归档站很慢。

### Kafka（log，这一轮新登记）

配置键两个：安装目录与 `bootstrap_servers`。契约在 `executors/contracts-oss-kafka.md`，
本地起停与冒烟配方在 `governance/oss-components.json`，由 `tools/oss_lab.py` 驱动。

关键纪律：**读回 0 行不算通过**——冒烟把"预期行数"当硬条件，与退出码无关。

**已真跑（2026-09-29）**：单机 KRaft 起得来，建 topic → 灌 5 行 → 从头上读回 5 行，
行数与灌入一致。三件踩出来的坑也都处置了：自带守护模式的进程活不过启动它的会话
（改用脱离会话的方式起，且启动器不能立刻退出）、进程存活判定会匹配到启动器自己的命令行
（改成探端口）、命令行工具的汇总行会被当成数据（按数据行的形状过滤）。
剩下没做的是**跨机器连通性**与多节点集群，见第七节。

### Spark（compute，这一轮新登记）

配置键只有 `home` 是判定项；连接器包与湖表 runtime jar 走 `kafka_package` / `lake_jars`。
契约在 `executors/contracts-oss-spark.md`。它与 Flink 是**同层的两条路**，
谁上由执行器仲裁规则决定，不由模型临场挑。

### Iceberg / Hudi / Delta（lake，这一轮新登记）

三者共用一份契约 `executors/contracts-oss-lakehouse.md`：它们都不是独立服务，
而是宿主引擎里的一个 catalog。判定键统一是 `runtime_jar`。
三者共用一个宿主引擎（Spark），所以注册表里 `host_engine` 都指向它。

### Pulsar / Debezium / Doris / StarRocks / ClickHouse（tier 3）

只登记角色与配置形状，**没有本地配方**，因此：

* 不参与"两条路选一条配全"的判定；
* `tools/oss_lab.py start` 会对它们直接报"注册表未提供启动配方"，不会假装能起；
* 校验器会拦"tier 3 却带了启动配方"这种自相矛盾的写法。

要升级成 tier 2，需要补齐：具体版本的构件地址、起停配方、就绪探针、冒烟步骤四样，
然后按同一套判据真跑一遍。

## 三、这一轮的优化与新增（2026-09-29）

排查出的问题按"是不是真问题"分两类，只列真的：

| # | 问题 | 证据 | 处置 |
| --- | --- | --- | --- |
| 1 | 开源执行器清单有**三份副本**（引擎里手写、契约文档、能力矩阵），加组件要改四处且无人校验 | `engine/core.py` 原先手写 `oss_flink/oss_paimon/oss_fluss` 三个键 | 引擎改为从注册表读 tier 1/2 组件，三份绑成一份 |
| 2 | 开源路径"配全"用 `all(...)` 判定，注册表一扩就把"只配 Flink + Fluss"的人误报成没配齐 | `engine/core.py` 的 `path_state["oss"]["complete"]` | 改为按**已开始的子集**判定：动过的必须配全，没动过的不算缺口 |
| 3 | 注册表读不出来时会静默变成"没有开源执行器"，把配置错误伪装成"没配" | 同上 | 注册表读取失败时进 `gaps`，显式报出 |
| 4 | 本地"装 + 起 + 停 + 冒烟"全靠人记在文档里，没有可执行入口，也没人管"同时只起一个" | 原先只有 `docs/oss-lab.md` 的手工步骤 | 新增 `tools/oss_lab.py`：注册表驱动、一次只起一个重型组件、冒烟输出落盘 |
| 5 | 主流实时组件覆盖只有 Flink / Paimon / Fluss 三件 | `governance/capability-matrix.json` 原先只有三条 `oss_*` | 注册表扩到 13 个组件，新增 Kafka / Spark / 湖表三件契约 |
| 6 | 校验器只查能力矩阵里的文件引用，不查注册表与契约、矩阵是否对得上 | `tools/validate_plugin.py` 第 3 项 | 第 3 项扩成"矩阵引用 + 注册表一致性" |
| 7 | 带 `~` 的路径交给 shell 有两种错法：被引号裹成字面量，或用**宿主平台的** Path 拼父目录（Windows 上给出 `~\oss`，那是另一个目录名） | 实测安装包被解到工作目录下一个带 `~` 的目录，而目标目录仍是空的 | 统一换成 `$HOME`；父目录改用 `posixpath`，并加用例断言生成的脚本里没有反斜杠 |
| 8 | 组件自带的守护模式起的进程活不过启动它的会话；改成 `setsid` 后，启动器立刻退出同样会带走刚 fork 的进程 | Kafka 连续三次起不来，连日志文件都没被创建 | 配方改成"脱离会话启动 + 启动器多活几秒"；就绪探针按超时窗口反复探，一次探不通不判失败 |

## 四、口径与纪律

1. **"真跑通过"的判据不给特例**：命令可复现、原始输出留档、读回行数与真实值一致。
   运行不起来同样要留现场（镜像、端口、报错、内存峰值），结论写"未验证"。
2. **一次只起一个重型组件**：本机 7.7G 内存，同时开两个必然互相拖死，失败现场也分不清是谁的问题。
   `tools/oss_lab.py start` 会拦第二个，要换组件得显式停掉前一个。
3. **"命令失败"与"没有数据"分开记**：连接失败、表不存在、认证失败都记失败并保留原文，
   不许写成"暂无数据"或"未发布"。
4. **占位符不算已配置**：引擎、薄封装 CLI、实验台用的是同一条判定规则。
5. **组件知识不进契约正文**：版本、端口、构件地址只在注册表里；契约只写形状与边界。

## 五、复现步骤

```bash
# 1. 看登记了什么、哪些构件还没配
py -3 tools/oss_lab.py list

# 2. 看某个组件在本机怎么起、冒烟跑哪几步（只打印，不执行）
py -3 tools/oss_lab.py plan oss_kafka

# 3. 起起来（有别的重型组件在跑会被拦，加 --stop-others 会先停掉它）
py -3 tools/oss_lab.py start oss_kafka

# 4. 真跑冒烟：建 topic → 灌 N 行 → 从头读回 N 行，原始输出落盘
py -3 tools/oss_lab.py smoke oss_kafka --topic rtd_lab_smoke --count 3

# 5. 停掉再上下一个组件
py -3 tools/oss_lab.py stop oss_kafka
```

本机设置在 `.rtd/lab.json`（模板 `templates/lab.example.json`）：装在哪、用什么壳跑。
Windows 上的 runner 一般填 `wsl -d <发行版> -- bash -lc`。

## 六、本轮实测记录

原始输出在 `docs/oss-lab.md` 第十三节与 `.tmp/lab/kafka2/`（每次冒烟都落盘，不进仓库）。
这里只写结论：

| 项 | 结论 |
| --- | --- |
| 版本选型 | 原定 3.9.2 只在归档站上有，实测 13.8 KB/s，放弃；改用快镜像上还在的 4.1.2（实测 2.7 MB/s） |
| 构件 | 从登记表里的镜像下载，133 MB，与登记版本一致 |
| 起 | 单机 KRaft：格式化存储 → 脱离会话启动 → 就绪探针经 runner 判定 9092 可连接 |
| 冒烟 | 建 topic → 灌 5 行 → 从头上读回 5 行，全部通过，原始输出落盘 |
| 停 | 停止脚本可用，端口随之下线；状态文件同步清空 |
| 未覆盖 | 多节点集群、跨机器（Windows 侧直连 WSL 端口）、认证与 ACL、Kafka 4.x 与 Flink 连接器联动 |

## 七、下一步（按依赖排序）

1. **跨组件主链路**：Flink SQL 的 Kafka 连接器写一张表、读回来，把"消息层 + 计算层"接上
   （本轮的组件都是各自独立跑通的，这一条要的是它们之间的联动）；
2. **Spark 读 Kafka**：Structured Streaming 从消息队列读、落到湖表——需要先补 Kafka 连接器构件；
3. **Pulsar / Doris / StarRocks 的构件来源**：找到能在几分钟内拉下来的源，再补配方与真跑；
   Doris 还要先确认内存够（单机 FE+BE 约 4GB，本机常驻已占 2.8GB）；
4. **跨机器连通性**：确认 Windows 侧能不能直连 WSL 的端口（当前探针已固定走 runner）；
5. **把这一轮的经验回灌契约**：Spark 的工作目录、Delta 的依赖闭包、Connect 的插件目录规则
   都已经写进对应契约与注册表的已知缺口，后续换版本时先读它们。

## 八、本轮全量真跑结果（2026-09-29）

按用户要求"全部组件都真实测试通过"，逐个起、逐个跑，判据统一是写进去多少行、读回来多少行。

| 结果 | 组件 |
| --- | --- |
| **真跑通过（12）** | Flink、Paimon、Fluss、Kafka、Spark（Structured Streaming）、Iceberg、Hudi、Delta、ClickHouse、Debezium、Pulsar、StarRocks |
| **未跑通（1）** | Doris（镜像已就位，BE 镜像拉取未完成，见 `docs/oss-lab.md` 十八节） |

十二项通过的具体读数：Spark 流式 3 写 3 读；Iceberg / Hudi / Delta 各 5 写 5 读；
ClickHouse 7 写 7 读；Debezium 源库 3 行 → CDC 3 条事件；Flink / Paimon / Fluss 见前几轮的记录
（行级读写与作业终态）；Kafka 5 写 5 读；Pulsar 灌 9 条、按最早位点读回 3 条；
StarRocks 写 5 读 5（BE 心跳为真）。

Doris 未跑通的原因是**镜像体积与拉取时间**，不是配方：它与 StarRocks 复用同一份编排脚本，
FE 镜像已就位，BE 镜像仍在拉取。注册表里保持如实状态，不预填结论。

### 补记：GitHub 通道的复测（2026-09-30）

上一轮说"GitHub 拉不动"是错的——同一地址复测是 744 KB/s。但改用 GitHub 也拿不到这两项：
`apache/doris` 与 `StarRocks/starrocks` 的 Release **不挂二进制资产**（逐个查过 `assets`）。
所以这不是通道问题，是上游的分发选择；要推进得另找分发入口。
