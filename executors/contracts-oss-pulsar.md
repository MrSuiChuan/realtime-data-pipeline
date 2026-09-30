# 开源栈执行器契约：Apache Pulsar

Pulsar 在插件里与 Kafka 同层，扮演**消息 / 日志存储**。注册表里是 `launch_mode = service`，
本地方案是单机 standalone（一个进程里同时是 broker 与 bookie）。

## 配置形状

```json
{
  "executors": {
    "oss_pulsar": {
      "home": "<Pulsar 安装目录>",
      "service_url": "<host:port，二进制协议端口>",
      "admin_url": "<管理 REST 的基地址>"
    }
  }
}
```

`service_url` 是判定"已配置"的关键键，也是就绪探针的目标；`admin_url` 供建命名空间与巡检使用。

## 使用契约

| 动作 | 约定 |
| --- | --- |
| 启动 | `pulsar-daemon start standalone` 起，**脱离启动会话**（见已知缺口） |
| 命名空间 | 端口通了**不等于** broker 初始化完了；冒烟的第一步是确认 `public/default` 真的存在 |
| 写入 | 走客户端工具的多条消息写法；写入失败与"写进去 0 条"分开记 |
| 读回（取证） | 按**最早的订阅位置**读回固定条数，读到几条内容行就是几条证据 |
| 巡检 | 只读 topic 元数据与订阅状态；不删订阅、不删 topic |

## 已知缺口（实测）

| 缺口 | 事实 | 处置 |
| --- | --- | --- |
| 就绪判定不能只看端口 | 二进制端口先开，命名空间还没建好，此前的写入会报 `Namespace not found` | 就绪探针保留端口，但冒烟加一步"确认命名空间存在" |
| 订阅位置只在创建时生效 | 订阅名固定时，第二次跑会接着上次的位点，读不到旧消息 | 读回时显式声明订阅位置；需要重跑就换订阅名或先删订阅 |
| 客户端参数名易错 | 位置参数是 `--subscription-position`（不是 `--subscription-initial-position`） | 以 `pulsar-client consume --help` 为准，别凭记忆写 |
| 配置脚本里别用复杂复合语句 | 配方里那种带子 shell 的 `for` 循环在经命令行层传递时被拆行，bash 报 `syntax error` | 配方里的准备步骤保持简单：两条 `curl` 的短路写法就够 |
