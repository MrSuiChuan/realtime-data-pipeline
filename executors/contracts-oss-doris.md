# 开源栈执行器契约：Apache Doris

Doris 在插件里扮演**实时分析 / 服务层**，与 StarRocks 同架构血统。注册表里是
`launch_mode = service`，本地方案是 FE 与 BE 各一个容器。

> **当前状态：未跑通。** 契约先写好是为了把"该用什么通道、该判什么"钉住；
> 验证状态以 `governance/oss-components.json` 的 `verified` 字段为准——它现在是空的。

## 配置形状

```json
{
  "executors": {
    "oss_doris": {
      "fe_image": "<FE 镜像>",
      "be_image": "<BE 镜像>",
      "mysql_endpoint": "<host:查询端口>",
      "container_prefix": "<容器名前缀>",
      "network": "<容器网络>"
    }
  }
}
```

判定"已配置"的关键键是镜像与查询入口。

## 分发通道：与 StarRocks 同一条

安装包这条路走不通，实测记录如下（不要在别处重试一遍）：

| 通道 | 结果 |
| --- | --- |
| GitHub Release 的 `assets` | 空（逐个版本查过） |
| 官方对象存储（加速域名） | 直链 404，且拒绝目录列举 |
| Apache 镜像站 | 老版本已撤，返回 403；归档站上的直链 404 |
| **容器镜像** | 可达：FE 镜像已从本机配置的镜像源拉到 |

## 使用契约

与 StarRocks 共用 `tools/lab/serving_cluster_up.sh` 与 `tools/lab/serving_smoke.sh`，
只换镜像与容器内路径（`/opt/apache-doris/{fe,be}`）。判据也一致：

| 动作 | 约定 |
| --- | --- |
| 起 | FE 与 BE 各一个容器；查询端口发布到宿主机 |
| 等就绪 | 必须等 BE 心跳为真；**只看端口会建表失败**（此时没有可用 BE） |
| 建库建表 | 由执行器执行；分布键、分桶、副本数来自工单 |
| 取证 | 读回行数：写 N 行、再从同一张表读回，行数一致才算过 |
| 巡检 | 只读系统表；不做 tablet 修复与 schema 变更 |

## 已知缺口

| 缺口 | 事实 | 处置 |
| --- | --- | --- |
| 镜像入口要环境变量 | 与 StarRocks 不同，Doris 镜像的入口脚本**没有环境变量就直接退出**（日志只列了五种参数组合） | FE 给 `FE_SERVERS=fe1:<fe>:8030` + `FE_ID=1`；BE 给 `FE_SERVERS=...` + `BE_ADDR=<be>:9050` |
| `BE_ADDR` 不是 IP | 只写 IP 会报 `BE_ADDR rule error！example: $BE_IP:$HEARTBEAT_SERVICE_PORT` | 必须写成 `IP:9050`（心跳端口） |
| 内核参数 | BE 启动前检查 `vm.max_map_count`，要求 ≥ 2000000（WSL 默认远低于此） | `wsl -u root sysctl -w vm.max_map_count=2000000`；这是**每次 WSL 重启后都要重做**的临时设置 |
| 必须关 swap | BE 检查到 swap 会直接拒绝启动（`Disable swap memory before starting be`） | 实验前 `swapoff -a`；注意 WSL 的 swap 由 Windows 侧管理，`swapon -a` 恢复不了，**重启 WSL 才恢复** |
| 默认堆 8 GB | FE 的 `fe.conf` 里 JDK17 用的是 `-Xmx8192m -Xms8192m`；本机总共 7.8 GB，关掉 swap 后 JVM 直接 `os::commit_memory ... Not enough space` | 跑通前必须把 FE 堆调小（需要覆盖镜像内的 `fe.conf`，当前编排脚本还不支持自定义命令） |
| 与 StarRocks 同端口 | 两家默认都用 9030，实验台的"一次只起一个"守卫按端口判定会把在跑的 Doris 误判成 StarRocks | 端口重叠时不要用端口做归属判定；先 `oss_lab stop` 掉另一个再用 `--stop-others` |
| BE 镜像体积与拉取时间 | 本机镜像源对 BE 镜像明显慢于 FE，前三次拉取分别在 22/25/30 分钟被超时截断 | 拉取用长超时并保留真实退出码；第四次（带缓存续传）成功 |

## 当前到哪一步（2026-10-01）

构件、编排、注册表条目、契约都到位；FE 已经能起来并响应查询端口，BE 也能注册进 FE。
**卡在内存账**：BE 要求关 swap，而 FE 默认要 8 GB 堆，7.8 GB 的机器上两者不可兼得。
下一步是给编排脚本加"自定义容器命令/挂载 fe.conf"的能力，把 FE 堆降到 2 GB 上下再试。
