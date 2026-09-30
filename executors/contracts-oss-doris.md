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
| BE 镜像体积与拉取时间 | 本机镜像源对 BE 镜像明显慢于 FE，多次拉取被超时截断 | 拉取用长超时并保留真实退出码；不要用管道把退出码盖掉 |
| 与 StarRocks 互斥 | 两家合计 4 GB 上下内存 | 一次只起一个；起之前先停掉另一个 |
| 就绪要等心跳 | 与 StarRocks 同一个坑 | 复用同一份编排脚本的等待逻辑 |
