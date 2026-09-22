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
./bin/sql-client.sh -f /mnt/c/Users/wuzongyun/Documents/ChatGPT/realtime-data-plugin/.tmp/oss-lab/flink-batch.sql
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
