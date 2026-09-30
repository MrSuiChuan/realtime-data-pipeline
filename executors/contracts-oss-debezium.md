# 开源栈执行器契约：Debezium（CDC）

Debezium 在插件里扮演**变更数据捕获**：把源库的变更变成事件，落到日志层供下游消费。
它是本仓库里唯一的**复合形态**组件——连接器不是进程，它跑在 Connect worker 上，
源头是数据库、落点是消息队列，四样都要在位。

## 配置形状

```json
{
  "executors": {
    "oss_debezium": {
      "home": "<连接器目录>",
      "plugin_dir": "<同一个目录；Connect 的 plugin.path 会取它的父目录>",
      "connect_url": "http://<host:port>",
      "pg_port": "<实验源库端口>",
      "pg_data": "<实验源库数据目录>"
    }
  }
}
```

## 使用契约

| 动作 | 约定 |
| --- | --- |
| 源库 | **用独立的实验实例**，不动共享实例：逻辑复制要求 `wal_level=logical`，改共享实例等于改别人的环境 |
| worker | Connect 由执行侧拉起；`plugin.path` 指向**只放这一个插件**的父目录 |
| 连接器 | 连接器配置里只写库、表与前缀；账号与端口来自配置 |
| 取证 | **读回事件条数**：源库写 N 行 → 从 CDC topic 读回 N 条事件，条数一致才算过 |
| 巡检 | 读连接器状态与 topic 维度；不删 replication slot、不改源库参数 |

## 已知缺口（实测）

| 缺口 | 事实 | 处置 |
| --- | --- | --- |
| `plugin.path` 要给父目录 | 直接指到装 jar 的目录时，Connect 逐个 jar 建类加载器，连接器找不到同目录的 `debezium-core`，报 `NoClassDefFoundError` | 父目录下只放这一个插件目录，让整目录进同一个类加载器 |
| 父目录要保持干净 | 父目录里放着 Flink / Spark / ClickHouse 时，worker 每次启动都要把它们扫一遍（实测多花几十秒） | 给插件单独一个父目录 |
| 重装要清目录 | 混装两个版本（旧版本 jar 没删）会让 worker 在插件扫描阶段直接失败 | 安装步骤先清目标目录再解包 |
| 版本与 Connect 的对齐 | 实测某版本与 Kafka Connect 4.x 的插件版本解析不兼容，换到 3.6.x 系可用 | 换版本要真起一次 worker，别只看下载成功 |
| 源库前置 | 必须开逻辑复制并留够复制槽；只读账号不行 | 实验实例由脚本自己 initdb 与启动，参数写在脚本里 |
