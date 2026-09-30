# 开源栈执行器契约：Apache Spark（Structured Streaming）

Spark 在插件里扮演**第二条流计算路径**：与 Flink 同层，但接口形态是 DataFrame / SQL 编程式提交，
不是常驻 SQL 会话。注册表里它是 `launch_mode = service`，探针是 `spark-submit --version`——
它没有常驻集群进程，"起来了"指的是本机可提交作业。

## 配置形状

```json
{
  "executors": {
    "oss_spark": {
      "home": "<Spark 安装目录>",
      "master": "<local[N] 或集群地址>",
      "kafka_package": "<spark-sql-kafka 连接器坐标>",
      "lake_jars": ["<湖表格式的 runtime jar 路径>"]
    }
  }
}
```

只有 `home` 是判定"已配置"的关键键；其余缺省时按引擎默认走，但**缺哪条就要在证据里说明**，
不许把"没带连接器包"写成"作业失败原因未知"。

## 与 Flink 的分工

| 维度 | Flink 路径 | Spark 路径 |
| --- | --- | --- |
| 提交形态 | SQL 客户端 `-f` 跑脚本，或 Gateway REST | `spark-submit` 提交程序文件 |
| 长驻作业 | 提交后回 Job ID，用 REST 查终态 | 由应用自己结束或常驻，终态看退出码与查询进度 |
| 取证 | REST 原生 JSON + SQL 客户端输出解析 | 作业日志与退出码，落地数据用宿主引擎再查一遍 |

两条路**不互替**：同一份工单要在哪条路上交付，由执行器仲裁规则决定，不由模型临场挑。

## 使用契约

| 动作 | 约定 |
| --- | --- |
| 提交 | 一律 `spark-submit`，参数与 jar 依赖来自项目配置，不写死在脚本里 |
| 流作业 | 必须设 checkpoint 目录；没有 checkpoint 的流作业不算可恢复 |
| 读回验证 | 用另一条批查询读回落地结果，不用流作业自己的日志自证 |
| 湖表写入 | 走湖表格式的 catalog，runtime jar 版本必须与 Spark 大版本、Scala 版本对齐 |
| 巡检 | 只读作业日志与 catalog 元数据；不 stop 别人的作业 |

## 已知缺口（登记在案）

| 缺口 | 事实 | 处置 |
| --- | --- | --- |
| Scala 版本对齐 | Spark 4.x 发行包是 Scala 2.13，连接器与湖表 runtime jar 都必须带 `_2.13` 构件 | 按发行包实际版本核对构件后缀，不凭记忆选 |
| 连接器要显式带包 | 发行包不含 Kafka 连接器 | 用 `--packages` 或 `--jars` 显式带，且把坐标写进项目配置 |
| 首次运行要拉依赖 | 依赖解析默认走公网仓库，首次会慢并产生本地 ivy 缓存 | 缓存目录写在项目侧，不进仓库 |
| 内存占用 | 即便 `local[1]` 也会起一个 JVM 与 UI | 与其它重型组件互斥，一次只起一个 |

## 本地实验台

`tools/oss_lab.py` 提供就绪探针与冒烟入口；Spark 的冒烟配方要真跑一段 Structured Streaming，
把作业日志与落地行数一起留档。**在真跑通过之前，能力矩阵里这一项的状态就是"未验证"。**
