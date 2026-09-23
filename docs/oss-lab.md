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
