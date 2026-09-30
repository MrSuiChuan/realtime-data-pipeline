# 本地开源实时栈实验环境

插件要能面向开源实时组件开发，就得有**真跑得起来的环境**。本文件记录本地 WSL 里装了什么、怎么起停、跑通了什么、踩了哪些坑。所有命令都可照抄复现。

环境：WSL2 / Debian 13 (trixie)，OpenJDK 21.0.10，Python 3.13.5，Docker 26.1.5，磁盘 907G 可用，内存 7.7G。

## 一、版本选型（按可下载构件核对过，不是凭记忆）

| 组件 | 版本 | 来源 | 备注 |
| --- | --- | --- | --- |
| Flink | 2.2.0 | `https://archive.apache.org/dist/flink/flink-2.2.0/flink-2.2.0-bin-scala_2.12.tgz`（543 MB） | Java 21 匹配 Flink 2.x |
| Paimon 连接器 | 1.4.1（`paimon-flink-2.2`） | Maven Central `org.apache.paimon:paimon-flink-2.2:1.4.1` | 与 Flink 2.2 对齐 |
| Fluss | 1.0.0 | `https://archive.apache.org/dist/fluss/fluss-1.0.0/fluss-1.0.0-bin.tgz` | 发行版目录只有 1.0.0 |
| Fluss 连接器 | 1.0.0（`fluss-flink-2.2`） | Maven Central `org.apache.fluss:fluss-flink-2.2:1.0.0` | 与 Flink 2.2 对齐 |

校验：Flink 发行包按官方 `.sha512` 比对通过

```
期望 3e6a7d25…fff5020
实际 3e6a7d25…fff5020   校验通过
```

## 二、目录与起停

```
~/oss/                                   # 安装根目录
├── flink-2.2.0/                          # 解压自发行包
│   ├── bin/{start-cluster.sh,stop-cluster.sh,sql-client.sh,flink}
│   ├── conf/flink-conf.yaml
│   └── log/
├── flink-2.2.0-bin-scala_2.12.tgz
└── dl-flink.log
```

启动（**必须在长驻会话里起**，见下面第 5 条坑）：

```bash
cd ~/oss/flink-2.2.0
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
./bin/start-cluster.sh
```

停：

```bash
./bin/stop-cluster.sh
```

Web UI 与探活：

```bash
curl -s http://127.0.0.1:8081/overview
# {"taskmanagers":1,"slots-total":1,"slots-available":1,...,"flink-version":"2.2.0"}
```

## 三、跑通了什么（RTD-030）

### 1. SQL 客户端连得上、批作业出结果

脚本 `.tmp/oss-lab/flink-batch.sql`（datagen 造 5 行 + SELECT）：

```bash
./bin/sql-client.sh -f <仓库路径>/.tmp/oss-lab/flink-batch.sql    # WSL 里通常写作 /mnt/c/... 或 ~/...
```

结果：

```
Flink SQL> +----+------+
| id | name |
+----+------+
|  1 | bb70 |
|  2 | da7d |
|  3 | 0e96 |
|  4 | 11fc |
|  5 | a835 |
+----+------+
5 rows in set (15.01 seconds)
```

### 2. 流作业提交 → 跑完 → TaskManager 日志里有真实行

脚本 `.tmp/oss-lab/flink-stream.sql`（datagen 5 行/秒、满 20 行结束，写 print sink）：

```
Job ID: fa8fc316e07474bfce7a980495ac3ba3
state: FINISHED
```

print sink 落在 TaskManager 的 **.out** 文件（不是 .log），共 20 行：

```
+I[1, 2026-09-22T01:29:40.949]
+I[2, 2026-09-22T01:29:40.956]
…
grep -hc "+I" log/flink-*-taskexecutor-*.out   → 20
```

## 四、给插件的直接结论

1. **执行器形态**：Flink 侧的"执行器"就是 `sql-client.sh -f <file>`（提交作业）+ REST API（查作业状态）。这两条都能当插件证据来源：作业 ID 与 `state` 是平台回读，不是自述。
2. **门控映射**：`compile_ok` 对应"SQL 语法/计划校验通过"；`publish_ok` 对应"作业提交成功且 REST 查到 Job ID"；巡检/诊断的数据源是 `/jobs/overview`、`/jobs/<id>`、TaskManager 日志。
3. **证据形态**：本项目 `rtd.py evidence add` 只收 JSON，而 `sql-client.sh -f` 输出是文本表格——联调时要让执行器输出结构化结果（REST 接口天然是 JSON，优先用 REST 取证，SQL 客户端只用于提交）。

## 五、踩过的坑（写下来免得重复踩）

1. **`start-cluster.sh` 的守护进程会跟着会话收到 SIGHUP 被杀**。第一次起完，Web UI 200，但两秒后 JobManager 日志出现 `RECEIVED SIGNAL 1: SIGHUP` 并退出。`setsid nohup ... &` 在本环境下仍然被带走；可靠做法是**在一个长驻会话里启动集群**（会话持有终端，进程才不被回收），或在 Docker 里跑。
2. **非交互模式（`-f`）下查询必须用 TABLEAU**。否则客户端报 `In non-interactive mode, it only supports to use TABLEAU as value of sql-client.execution.result-mode`。脚本里要显式 `SET 'sql-client.execution.result-mode' = 'tableau';`。
3. **时间戳看着不对**：print 出来是 `01:29`，而机器本地时间 `09:29`。SQL 会话默认时区是 UTC，验证时间语义前先确认 `table.local-time-zone`——这正是插件里"时间必须带时区"那条纪律的现实版。
4. **任务槽要等**：`start-cluster.sh` 返回后 TaskManager 还没注册完，立刻查 `/overview` 会看到 `taskmanagers: 0`。等几秒再查，别急着下"起不来"的结论。
5. **SQL 文件别在 PowerShell 里用 here-doc 拼**：引号会被吃掉，落成半个文件。写成文件走 `/mnt/c/...` 路径最稳（本目录 `.tmp/oss-lab/` 就是这么来的）。

## 六、待办

- Paimon 连接器与 Fluss 的安装与验证（RTD-031 / RTD-032）——本文件继续追加。
- 用 Flink REST + SQL 客户端做插件端到端链路（RTD-033）。

## 七、Paimon 安装进展与卡点（2026-09-22）

已下载：`paimon-flink-2.2-1.4.1.jar`（54 MB，来自 Maven Central），已放进 `~/oss/flink-2.2.0/lib/` 并重启集群。

**卡点**：创建 Paimon catalog 时报

```
java.lang.ClassNotFoundException: org.apache.hadoop.conf.Configuration
```

原因：Paimon 的 filesystem catalog 走 Hadoop FileSystem API，而 **Flink 2.2.0 不再自带 shaded Hadoop**（`lib/` 里没有任何 hadoop jar，`opt/` 只有 S3/OSS/GS/Azure 插件）。需要在 `lib/` 里补 `flink-shaded-hadoop-2-uber`（或等价 hadoop-common 依赖）。

**当时的网络状态**：DNS 解析失败（`Could not resolve host: repo1.maven.org`，Windows 侧与 WSL 侧同时失效），因此这一步的依赖下载被迫中断。恢复后继续：下载 shaded hadoop uber → 放进 `lib/` → 重启集群 → 重跑 `paimon-write.sql` / `paimon-read.sql`。

已落好的验证脚本（网络恢复后直接用）：

| 脚本 | 做什么 |
| --- | --- |
| `.tmp/oss-lab/paimon-write.sql` | 建 Paimon catalog 与主键表，datagen 造 10 行流式写入（含 3 秒检查点） |
| `.tmp/oss-lab/paimon-read.sql` | 批模式读回：行数 + 前 5 行明细 |

## 八、Paimon 已跑通（2026-09-22 晚）

补齐 `flink-shaded-hadoop-2-uber-2.8.3-10.0.jar` 到 `lib/` 后，`ClassNotFoundException` 消失，链路全通：

**1. 流式入湖**

```
CREATE CATALOG paimon / CREATE DATABASE db_lab / CREATE TABLE t_orders(主键 + 按 dt 分区)  全部 Execute statement succeeded
INSERT 提交成功：Job ID 87f7e97028abddf2f227414fcaaf623e
作业终态：FINISHED
```

落盘结构：

```
/tmp/paimon-warehouse/db_lab.db/t_orders/{snapshot,manifest,schema,dt=2026-09-22/bucket-0/data-*.parquet}
```

**2. 读回验证（批模式）**

```
| cnt |
|  10 |        → 1 row in set
| order_id |      amount |         dt |   → 5 rows，order_id 1..5，dt=2026-09-22
```

**3. 结论**：Paimon 作为"湖表目录"在本地可用；`governance/capability-matrix.json` 里 `oss_paimon.filesystem-catalog` 的 blocked 状态已解除，前置条件是 shaded Hadoop 必须进 `lib/`。

## 九、SQL Gateway 取证通道（2026-09-22 晚）

插件要求证据是结构化 JSON，所以启用了 Flink 自带的 SQL Gateway REST（8003 端口那一类用法）：

```
./bin/sql-gateway.sh start-foreground     → Rest endpoint listening at localhost:8083
```

踩到的四个坑（都写进脚本注释了）：

1. **必须显式配置 `sql-gateway.endpoint.rest.address`**，否则启动即报 `Missing required options: address`；Flink 2.2 的配置文件名是 `conf/config.yaml`；
2. **操作是异步的**：提交语句拿到 `operationHandle` 后要先轮询 `/status` 到 `FINISHED`，再去 `/result/0` 取数，否则只会拿到空；
3. **批模式下结果页是空的**（实测），流模式反而能拿到完整 changelog——`{"kind":"UPDATE_AFTER","fields":[10]}`，取最后一条非 `UPDATE_BEFORE` 的值就是终值；
4. `nextResultUri` 是**相对路径**，要自己拼上 gateway 前缀。

## 十、插件端到端链路跑通（RTD-033）

取证脚本：`.tmp/oss-lab/flink_gateway_evidence.py`，两条通道：

| 通道 | 说明 |
| --- | --- |
| `--via gateway` | 走 SQL Gateway REST 直接拿 JSON（结构最干净，但计数查询页面翻不完，实测不稳） |
| `--via client` | 跑 `sql-client.sh -f paimon-read.sql`，解析真实输出成契约 JSON，**原始输出一并留档** `paimon-read-raw.txt` |

实际用的是 client 通道，产出的证据：

```json
{
  "observed_at": "2026-09-22T21:11:09+08:00",
  "source": "flink-sql-client",
  "command": "…/sql-client.sh -f …/paimon-read.sql",
  "exit_code": 0,
  "tables": [{"name": "paimon.db_lab.t_orders", "published": true, "rows": 10, "query": "SELECT COUNT(*) AS cnt …"}]
}
```

拿着它跑插件自己的流程（命令与输出都是实跑）：

```
rtd.py setup                        → 运行时建好，引擎自拷贝进 .rtd/engine/
rtd.py object set --file-id paimon.db_lab.t_orders --source flink-sql-client
rtd.py evidence add --kind refs_readback --from refs_readback.json --tool flink-sql-client --command "sql-client.sh -f paimon-read.sql"
   → 校验通过：1 张引用表全部已发布；object_file_id 已记录
rtd.py gate set --name refs_published --evidence refs_readback-20260922211134-31ce69
rtd.py advance --phase design → build
rtd.py status  → phase=build, gates_satisfied=['refs_published'], evidence_count=1
rtd.py verify  → 运行时自检通过：状态、证据哈希、门控引用一致
```

顺带被自己的检查拦了一次：第一次直接 `advance --phase build` 被拒（"跨了中间阶段"）——那是 RTD-026 新增的规则在生效，改成 design → build 两步即通过。

**结论**：插件面向开源栈的链路是通的——`refs_readback` 证据来自真实的 Paimon 查询，门控按证据开，阶段推进受规则约束，运行时自检可复核。

## 十一、Fluss 已跑通（2026-09-22 晚）

### 下载：换国内镜像是关键

`archive.apache.org` 直连只有 **6.7 KB/s**（497 MB 要 20 小时），`dlcdn` / `downloads` 直连全 `http=000`。换国内镜像后：

| 源 | 实测速度 |
| --- | --- |
| mirrors.ustc.edu.cn | **11.4 MB/s**（43 秒下完 497 MB） |
| mirror.nju.edu.cn | 10.8 MB/s |
| mirrors.aliyun.com | 8.5 MB/s |
| archive.apache.org（直连） | 6.7 KB/s |

包与官方 `.sha512` 比对一致：

```
期望 4cc134d1…b7d52ca
实际 4cc134d1…b7d52ca   校验通过
```

**这条经验值得记住**：以后拉 Apache 发行包先试国内镜像，别跟 archive 直连死磕。

### 集群与读写（全部实测）

```
bin/local-cluster.sh start
→ Starting zookeeper daemon / coordinator-server daemon / tablet-server daemon
→ 端口：ZooKeeper 2181、Fluss 9123（listening 127.0.0.1:9123）
→ 日志：TabletServer registered、Coordinator 收到 CHILD_ADDED
```

`fluss-console.sh` **不是 SQL 控制台**（它只用来起 coordinator-server / tablet-server / zookeeper），所以入口就是 Flink SQL + Fluss 连接器：

```
cp fluss-flink-2.2-1.0.0.jar ~/oss/flink-2.2.0/lib/     # 之后重启 Flink 集群
CREATE CATALOG fluss WITH ('type'='fluss', 'bootstrap.servers'='localhost:9123')
CREATE DATABASE fluss.db_lab
CREATE TABLE fluss.db_lab.log_orders (order_id BIGINT, amount DECIMAL(10,2), dt STRING)   -- 默认是日志表
INSERT … SELECT … FROM datagen 源
→ Job ID ddfe7d21f2e79a90bb2fb62ab7734209，终态 FINISHED
→ 数据落盘：/tmp/fluss-data/db_lab/log_orders-0/log-0
```

读回（批模式）：

```
| cnt | → 10        （1 row in set, 9.42 秒）
| order_id | amount | dt | → 5 行，order_id 1..5，dt=2026-09-22
```

**结论**：Fluss 作为"流存储"在本地可用；契约里那条版本对齐矩阵（连接器按 Flink 版本分构件）得到验证——`fluss-flink-2.2-1.0.0.jar` 配 Flink 2.2.0 正常读写。

## 十二、薄封装 CLI 实跑（2026-09-23，RTD-037）

把 Flink/Fluss 的接口包成 `tools/oss_cli.py` 之后，用它把两条链路各跑了一遍。**下面每一条都是真跑的输出，不是设计意图**。

### 1. 起环境时先撞到两件事（都不是 CLI 的问题）

| 现象 | 现场 | 结论 |
| --- | --- | --- |
| 作业反复 `RESTARTING`，异常是 `NoResourceAvailableException: Could not acquire the minimum required resources` | `/overview` 显示 `taskmanagers: 0` | JobManager 在跑，TaskManager 早没了；`bin/taskmanager.sh start-foreground` 起来后作业立刻恢复并跑完 |
| Fluss 集群端口消失，coordinator 日志刷 `Connection refused localhost:2181` | zookeeper / coordinator / tablet 进程都在，但 zk 端口没了 | **Fluss 的守护进程与 Flink 一样会随启动它的会话被 SIGHUP 带走**；要在长驻会话里起（`local-cluster.sh start` 后让会话挂着） |

这两条与本文件第五节第 1 条同源：WSL 里"脚本返回了就以为服务在跑"，下次会话再来看才发现是空场。

### 2. 通过 CLI 建的 Paimon 表（`flink submit`）

```bash
python3 tools/oss_cli.py --project .tmp/oss-lab/project flink submit -f .tmp/oss-lab/paimon-write.sql
# Job ID: 798df2565d712d2277dc7776b7222ff7
python3 tools/oss_cli.py --project .tmp/oss-lab/project flink status 798df2565d712d2277dc7776b7222ff7
# 作业 798df… 状态：FINISHED
```

客户端通道的特征在这里看得最清楚：**提交是异步的**（打印 Job ID 后就关会话），真正的终态要去 REST 回读——所以"提交成功"与"作业跑完"是两条证据，不能互相顶替。

### 3. 两张表的引用回读（`evidence refs`）

```bash
python3 tools/oss_cli.py --project .tmp/oss-lab/project evidence refs \
  --table paimon.db_lab.t_orders --raw-dir .tmp/oss-lab/raw
# → published: true, rows: 10，退出码 0

python3 tools/oss_cli.py --project .tmp/oss-lab/project fluss sql -f .tmp/oss-lab/fluss-write.sql
# CREATE CATALOG fluss / CREATE DATABASE / CREATE TABLE / INSERT 全部 Execute statement succeeded
# Job ID: 0eb6a7626a4cd27749a5fcd255a43656 → FINISHED

python3 tools/oss_cli.py --project .tmp/oss-lab/project evidence refs \
  --table fluss.db_lab.log_orders --raw-dir .tmp/oss-lab/raw
# → published: true, rows: 10，退出码 0
```

`fluss.*` 这张表是同一个 `evidence refs` 读的：脚本按表名前缀现建 `fluss` catalog，所以不需要为 Fluss 单开一条通道。

### 4. 失败案例（这条是本轮修的东西）

```bash
python3 tools/oss_cli.py --project .tmp/oss-lab/project evidence refs --table paimon.db_lab.t_missing
# rc 2
# "published": null, "rows": null,
# "error": "Could not execute SQL statement. Reason: … Object 't_missing' not found within 'paimon.db_lab'"
```

**修之前**这里会落成 `published: false, rows: null`——把"查失败"写成了"表没数据"，正好是插件宪法里"查询失败≠零事件"那条要拦的事。
根因是 SQL 客户端**语句失败时退出码仍是 0**，错误只在输出的 `[ERROR]` 段里；现在成败按文本判定，解析不出结果也记 `null` + 原因，绝不降级成"未发布"。

### 5. 客户端输出格式的两个坑（写进了解析器）

```
Flink SQL> 
> SELECT COUNT(*)+-----+
| cnt |
+-----+
|  10 |
+-----+
1 row in set (21.45 seconds)
```

1. 表格边框被**粘在语句 echo 后面**（`SELECT COUNT(*)+-----+`），所以解析不能按行号硬切，只能按列名锚定；
2. 计数查询在**批模式**下必须显式 `SET 'execution.runtime-mode' = 'batch'`，结果模式必须 `tableau`（非交互模式只认它）。

### 6. 结论与边界

| 项 | 结论 |
| --- | --- |
| Flink 作业查询/异常 | 走 REST，返回原生 JSON，已实跑 |
| Flink/Fluss SQL 执行 | 走 SQL 客户端，已实跑（建表 + 写入 + 读回） |
| 引用表证据 | `refs_readback` JSON 由真实 `COUNT` 产出，行数与真实值一致，原始输出留档在 `--raw-dir` |
| Gateway 通道 | 保留为 `--via gateway`，但取结果在 Flink 2.2 上不可靠（见第十节），**不当默认** |
| 运行位置 | CLI 必须跑在能连到集群的机器上；本地是"在 WSL 里跑"（Windows 侧直连被代理拦） |
| 未验证 | 跨机器 / 容器内 / 生产集群的连通性没测；工具覆盖 Flink 与 Fluss，Paimon 通过 Flink catalog 间接覆盖 |

## 十三、Kafka 真跑与本地实验台（2026-09-29，RTD-039 / RTD-041）

这一节的组件、路径与版本**不在文档里定**，只在 `governance/oss-components.json` 里登记；
起停与冒烟由 `tools/oss_lab.py` 读那份登记表执行。文档只记结论与现场。

### 1. 版本选型：先看快镜像上有没有

原定 3.9.2，实测只有归档站上有，**13.8 KB/s**，127 MB 要拉两个多小时，不可用。改选快镜像上还在的 4.1.2：

| 源 | HTTP | 实测速率 |
| --- | --- | --- |
| 国内某 apache 镜像（3.9.2） | 404 | — |
| 两个高校镜像（3.9.2） | 403 | — |
| 归档站（3.9.2） | 206 | 13.8 KB/s |
| 镜像（4.1.2） | 206 | **2.7 MB/s** |

结论：**选版本之前先确认镜像上还在**。归档站是最后手段，不是备选方案。

### 2. 起：单机 KRaft 的三件事

```
# 1) 把 log.dirs 指到实验目录（生成一份 lab-server.properties，不动发行包自带的配置）
# 2) 第一次启动前格式化存储（存在 meta.properties 就跳过）
kafka-storage.sh format -t <随机 uuid> -c lab-server.properties --standalone
# 3) 脱离会话启动，且启动器不能立刻退出
setsid nohup kafka-server-start.sh lab-server.properties > logs/server.out 2>&1 < /dev/null & sleep 8
```

第 3 条是这一轮最难的一步，踩了两层：

* `kafka-server-start.sh -daemon` 起的进程**随启动它的那个会话被杀**（与 Flink / Fluss 同一个坑）；
* 改成 `setsid nohup … &` 之后仍然起不来——因为启动器**立刻退出**，刚 fork 出来的进程还没 exec 就被会话回收带走了。
  给它 `sleep 8` 之后才稳定。判据是：日志文件被创建、端口能连上，两样都看得到才算数。

另外两处判定错误也记在这里，都不是 Kafka 的问题，是**方法论**的问题：

* **进程存活判定会"自己匹配自己"**：`pgrep -f kafka.Kafka` 会匹配到执行这条命令的启动器自己的命令行，
  于是永远判定"已经在跑"，服务根本没起。改成探端口。
* **启动到可用之间有延迟**：broker 进程起来后还要注册完才接受连接。就绪探针必须按超时窗口反复探，
  一次探不通就判失败会把正常启动误报成故障。

### 3. 冒烟：建 topic → 灌 5 行 → 从头上读回 5 行

```
$ py -3 tools/oss_lab.py smoke oss_kafka --topic rtd_lab_smoke2 --count 5 --out .tmp/lab/kafka2
[通过] topic-create —— rc 0，输出 2 行
[通过] produce —— rc 0，输出 0 行
[通过] consume-back —— rc 0，输出 5 行，预期 ≥ 5 行
原始输出：.tmp\lab\kafka2
```

**这里修掉了一个会让判据失真的点**：console consumer 读完会自己打印一行
`Processed a total of N messages`。按总行数判的话，读到 2 条 + 1 行汇总也能凑够"3 行"从而判通过。
所以配方里多了一条"数据行长什么样"的正则，只数匹配的行——这一条是读原始输出时发现的，不是推出来的。

### 4. 停与状态

停止脚本可用，端口随之下线，状态文件同步清空。`status` 会逐个组件探一次：
库形态（Paimon 这类）显示"不适用"，按需提交型引擎（Spark）显示"可提交"而不是"在跑"——
它没有常驻进程，"在跑"会把状态说成另一回事。

### 5. 未覆盖

多节点集群、跨机器连通性（Windows 侧直连 WSL 端口）、认证与 ACL、以及 Kafka 与计算引擎连接器的联动，
都还没做。这些在台账 `docs/oss-component-ledger.md` 的第七节列成了下一步。

## 十四、逐个真跑：Spark / 湖表 / ClickHouse / Debezium（2026-09-29，RTD-044–RTD-050）

这一轮把注册表里能拿到的组件**逐个起、逐个跑**，判据统一是"写进去多少行、读回来多少行"。
配方全部在 `governance/oss-components.json`，执行入口是 `tools/oss_lab.py smoke <组件>`，
原始输出落在 `.tmp/lab/<组件>/`（不进仓库）。

### 1. Spark：Structured Streaming

```
[通过] structured-streaming-run —— rc 0，输出 1 行，预期 ≥ 1 行，读数 3 应等于 3
```

rate 源 → Parquet（带 checkpoint）→ 批读回 3 行。两个必须写进配方的点：

* **工作目录**：Spark 会在当前目录建 Derby 元数据库（`metastore_db/`、`derby.log`）。
  不指定工作目录的话，这些残渣会落在调用者的项目里——实测踩过一次。配方里加了 `cwd` 字段。
* **行数要对得上**：rate 源每批不止一行，直接"来多少写多少"就没法按行数对账。
  写法是按还差几行 `limit` 后再写，这样读回的数是确定的。

### 2. 湖表三件：Iceberg / Hudi / Delta

都是宿主引擎里的 catalog，冒烟统一为：建命名空间 → 建表 → 写 5 行 → 批模式读回 5 行。

| 格式 | 结果 | 踩到的坑 |
| --- | --- | --- |
| Iceberg | 通过（5 读 5） | catalog 的 type 与 impl 要成对配置 |
| Hudi | 通过（5 读 5） | SQL DDL 必须同时挂 session extension 与 HoodieCatalog；且不支持 SQL DELETE 清表，重跑先 DROP |
| Delta | 通过（5 读 5） | **delta-spark 不是 fat jar**：只 `--jars` 一个 jar 会缺 `delta-storage`（实测 `NoClassDefFoundError: io/delta/storage/commit/actions/AbstractProtocol`），改成 `--packages` 让 Maven 解析闭包才对 |

### 3. ClickHouse：服务层

```
[通过] roundtrip —— rc 0，输出 1 行，预期 ≥ 1 行，读数 7 应等于 7
```

单二进制起 server：自写一份最小配置（数据/临时目录、端口、内存上限都在里面）。
**最小配置必须自带 `profiles` / `quotas` / `users` 三段**——只给路径和端口的话，
启动在 `setDefaultProfileName` 处直接失败，报错信息完全不提"缺哪段"。
停止按数据目录里的 `status` 文件取 PID，不用进程名匹配。

构件：从官方源取到 138 MB 的包，实测 928 KB/s；同一个包的 GitHub 直链实测**完全拉不动**（0 B/s）。
这条与 Kafka 那条是同一个教训：**先测速再定源**。

### 4. Debezium：CDC 全链路

这是本仓库唯一的复合形态组件，也是最费劲的一条：

```
Postgres 实验实例（wal_level=logical）→ Kafka Connect + Debezium → Kafka topic → 读回事件
[通过] postgres-to-kafka —— rc 0，输出 1 行，预期 ≥ 1 行，读数 3 应等于 3
```

四个坑，每个都花了时间：

1. **源库要独立**：逻辑复制要改 `wal_level`，不能动共享实例。脚本自己 `initdb` 一个实验实例，
   并顺手把 unix socket 目录挪到自己的目录（`/var/run/postgresql` 没权限，否则起不来）。
2. **`plugin.path` 要给父目录**：Connect 把该目录下的**每个子目录**当作一个插件（一个类加载器）。
   指到装 jar 的那个目录，它会逐个 jar 建类加载器，连接器就找不到同目录的 `debezium-core`。
3. **父目录要保持干净**：把 `plugin.path` 指到 `~/oss` 之后，worker 每次启动都要把
   Flink、Spark、ClickHouse 全扫一遍，几十秒都起不来。给插件单独一个父目录。
4. **重装要先清目标目录**：清之前混装了连接器的两个版本，worker 在插件扫描阶段就失败。
   顺带把这条做进了实验台的安装步骤（`rm -rf` 目标目录再解包），并加了路径合法性护栏。

另外记录一条版本兼容：连接器某一版与 Kafka Connect 4.1 的插件版本解析不兼容
（`Failed to get plugin version`），换到 3.6.x 系可用。**换版本必须真起一次 worker**，
下载成功不等于能用。

### 5. 三个没跑通的：Pulsar / Doris / StarRocks

这三个**不是配方没写，是构件拿不到**。留现场：

| 组件 | 实测 | 结论 |
| --- | --- | --- |
| Pulsar | closer 上的 3.3.9 是 9.6 KB/s；归档站 3.3.1 是 11 KB/s；国内镜像没有这个目录 | 按这个速度要几小时，未跑通 |
| Doris | 加速地址与归档站上的版本都是 404，镜像站对归档版本返回 403，下载页是 JS 渲染拿不到直链 | 构件来源没找到，未跑通 |
| StarRocks | `releases.starrocks.io` 对列表与直链都返回 403，归档站没有这个项目 | 它不是 ASF 项目，绕不过去，未跑通 |

还有一条与速度无关的前置：Doris 单机 FE+BE 要 4 GB 上下内存，
本机总共 7.8 G、常驻服务已占 2.8 G，**就算拿到构件也要先评估内存**。
这三项在注册表里保持"未验证"，不写推测结论。

## 十五、Pulsar 真跑与"从 GitHub 下载"的结论（2026-09-30）

### 1. 先纠正上一条结论：GitHub 是通的

上一轮测得 ClickHouse 的 GitHub 直链 0 B/s，当时的结论是"GitHub 拉不动"。这一轮复测：
**同一个直链 744 KB/s**。所以上一轮那个数是瞬时现象，不是通道问题——**测速要复测，一次采样不能当结论**。

### 2. 但 GitHub Release 上确实没有这三个项目的二进制

按用户要求改用 GitHub 渠道，先把三个项目的 Release 资产查了一遍（`/releases/tags/<tag>` 的 `assets`）：

| 项目 | GitHub Release 资产 |
| --- | --- |
| `apache/pulsar`（v4.0.13） | 无 |
| `apache/doris`（4.1.4） | 无 |
| `StarRocks/starrocks`（4.1.3） | 无 |

它们的二进制本来就不挂 GitHub，所以"从 GitHub 下载"这条路对这三个组件不成立。
**这不是通道问题，是上游的分发选择。**

### 3. 换云厂商镜像：Pulsar 通了

换到云厂商的 Apache 镜像后：

| 源 | 实测 |
| --- | --- |
| 归档站 3.3.1 | 11 KB/s |
| closer 上的 3.3.9 | 9.6 KB/s |
| 云厂商镜像上的 4.0.13 | **1.7 MB/s（实测下载全程均值 4.2 MB/s）** |

237 MB 的包一分钟出头拉完。起停与冒烟：

```
[通过] ensure-namespace —— rc 0，输出 1 行
[通过] produce —— rc 0，输出 12 行
[通过] consume-back —— rc 0，输出 3 行，预期 ≥ 3 行
```

三个坑记进了 `executors/contracts-oss-pulsar.md`：

1. **端口通了不等于初始化完了**：二进制端口先开，命名空间还没建，写入报 `Namespace not found`。
   冒烟的第一步改成"确认 `public/default` 存在"（GET 不通就 PUT 建）。
2. **位置参数名易错**：是 `--subscription-position`，不是 `--subscription-initial-position`。
   写错时客户端会把值当多出来的参数，报 `Unknown options`。
3. **配方里的准备步骤别写复合语句**：带子 shell 的 `for` 循环经命令行层传递后被拆行，
   bash 报 `syntax error near unexpected token`。改成两条 `curl` 的短路写法就好了。

### 4. Doris 与 StarRocks：这一轮仍然没跑通

| 组件 | 这一轮试过的 | 结果 |
| --- | --- | --- |
| Doris | GitHub Release 资产；云厂商镜像上的 2.1.8 / 3.0.3 直链 | 资产为空；两个直链都是 **404**（镜像站把老版本撤了） |
| StarRocks | GitHub Release 资产；云厂商镜像上的直链 | 资产为空；镜像站直链返回的是**网页**（200 但内容是 SPA 首页，不是文件），官方 CDN 仍是 403 |

结论保持"未跑通"，原因写清楚：**上游没有把二进制放到我们能取到的地方**。
要推进需要一条新的分发入口（内网仓库、对象存储镜像，或官方提供的新地址）。

## 十六、GitHub 到底有没有：把结论查实（2026-09-30）

上一轮说"这两个项目的 GitHub Release 没有二进制"，但那个结论是用 `grep` 过滤接口返回得出的——
**接口被限流或返回错误时，过滤结果同样是空**，等于把"没查到"当成了"没有"。这一轮用 JSON 正经解析复验：

```
限流：剩余 60/60
apache/doris      4.1.4.1 / 4.1.4 / 4.0.8 / 4.1.3 …  每个版本 assets 都是空的
StarRocks/starrocks 3.5.21 / 4.0.14 / 3.5.20 …        每个版本 assets 都是空的
```

限流没被消耗、HTTP 200、列表正常返回——**结论成立：这两个项目确实不把二进制挂在 GitHub Release 上**。
要分清两件事：**开源**指的是源码与许可证公开（两个项目都是），**二进制分发**是各自的选择
（Doris 走自己的对象存储，StarRocks 走官方 CDN）。它们 GitHub 上给的是源码，不是安装包。

## 十七、换一条通道：容器镜像（StarRocks 跑通）

既然安装包拿不到，就换分发通道。本机 Docker 配了国内镜像源，容器镜像这条路是通的——
而且**本机早就有 StarRocks 3.3.9 的 FE 与 BE 镜像**（别人早前拉过）：

```
docker.1ms.run/starrocks/fe-ubuntu:3.3.9   1.97GB
docker.1ms.run/starrocks/be-ubuntu:3.3.9   3.03GB
```

起停编排落成 `tools/lab/serving_cluster_up.sh`（Doris 与 StarRocks 共用一份，用参数区分路径）。
三个坑：

1. **镜像默认命令是 `bash`**：用普通分离方式起容器会立刻退出（`Exited (0)`），必须用交互式分离；
2. **BE 要显式声明对外网段**：容器里既有回环又有网卡，不指定就注册成错地址，
   FE 一直报 "No alive backend"；
3. **就绪要等心跳**：查询端口先开，此时 BE 还没注册，建表会因为"没有可用 BE"而失败。
   判据是 `Alive = true`，不是端口通。

结果：

```
rtd_backend_alive=true
[通过] roundtrip —— rc 0，输出 1 行，预期 ≥ 1 行，读数 5 应等于 5
```

**StarRocks 真跑通过**：建库建表（DUPLICATE KEY）写 5 行、读回 5 行。

## 十八、Doris：同一条通道

Doris 与 StarRocks 是同一个架构血统，容器布局几乎一致，所以直接复用同一份编排脚本
（只换镜像与容器内路径）。FE 镜像 `apache/doris:fe-3.0.3` 已从同一个镜像源拉到（2.24GB）；
BE 镜像体积更大，拉取仍在进行。这一节按实际结果补写，不预填结论。

## 十九、Doris：拉到构件之后卡在内存账（2026-10-01）

BE 镜像第四次拉取（带缓存续传）终于成功：**6.06 GB**。此后一路排查，结论是**没跑通**，
原因不在配方，而在内存。过程按顺序记下来：

### 1. 入口脚本要环境变量（与 StarRocks 不同）

第一次起容器直接退出，日志只列了五种参数组合：

```
[ERROR] [Entrypoint]: EOF
        Note that you did not configure the required parameters!
        plan 4: FE_SERVERS & FE_ID & BE_SERVERS & FQDN
```

FE 给 `FE_SERVERS=fe1:127.0.0.1:8030` + `FE_ID=1`；BE 给 `FE_SERVERS=...` + `BE_ADDR`。
`BE_ADDR` 不是 IP——只写 IP 会报 `BE_ADDR rule error！example: $BE_IP:$HEARTBEAT_SERVICE_PORT`，
要写 `127.0.0.1:9050`。

### 2. 两个内核前置

BE 启动前做两项检查，都不满足：

| 检查 | 报错 | 处置 |
| --- | --- | --- |
| `vm.max_map_count ≥ 2000000` | `Set kernel parameter 'vm.max_map_count' to a value greater than 2000000` | `wsl -u root sysctl -w vm.max_map_count=2000000`（WSL 重启后要重设） |
| 不能有 swap | `Disable swap memory before starting be` | `swapoff -a`；WSL 的 swap 由 Windows 侧管理，`swapon -a` 恢复不了，**重启 WSL 才恢复** |

### 3. 卡点：FE 默认要 8 GB 堆，BE 又要求关 swap

关掉 swap 之后 FE 反而起不来了：

```
OpenJDK 64-Bit Server VM warning: os::commit_memory(...) failed; error='Not enough space' (errno=12)
Native memory allocation (mmap) failed to map 8589934592 bytes
```

镜像里的 `fe.conf` 写着 `JAVA_OPTS_FOR_JDK_17="... -Xmx8192m -Xms8192m ..."`，
而本机总共 7.8 GB。**BE 要求关 swap + FE 要 8 GB 堆，在这台机器上不可兼得。**

### 4. 结论与下一步

构件、编排、注册表条目、契约都已到位；FE 能起来并响应查询端口，BE 能注册进 FE。
差的是**把 FE 堆降下来**（2 GB 上下），这需要给编排脚本加"自定义容器命令/挂载 fe.conf"的能力——
当前脚本还不支持覆盖镜像里的启动配置。这一步做完再继续跑冒烟。

顺带记一条实验台的坑：**Doris 与 StarRocks 默认都用 9030**，"一次只起一个"的守卫按端口判定，
会把在跑的 Doris 误判成 StarRocks。端口重叠时不能靠端口判归属，得先 `oss_lab stop` 掉另一个。
