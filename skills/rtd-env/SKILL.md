---
name: rtd-env
description: 执行器环境检查与接入（Codex 入口，等价于 /env）
---

# rtd-env（Codex 版 `/env`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/env.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-env — 执行器环境检查与接入

流程见 `workflows/runbook-environment.md`；接入纪律见 `governance/mcp-setup.md`。

## 三个模式

| 用户说 | 模式 | 行为 |
| --- | --- | --- |
| 检查 | check | 只查不装 |
| 安装/初始化 | install | 跳过已装的 |
| 更新 | update | 仅当明确有可用更新 |

```
py -3 .rtd/engine/rtd.py env check --json
```

## 三种状态别混

`配置存在` / `认证完成` / **当前会话可调用**——只有第三种算可用。引擎不做平台调用，认证与可调用要靠一次真实只读请求。

## 两条路，选一条配全

执行器分两组，`env check` 会分别判定：

| 路径 | 由什么组成 | 配全的标准 |
| --- | --- | --- |
| 平台路径 | `cli` + 各域 `mcp_*` | 至少一个平台执行器填全（`cli.cmd` 或某个 MCP 服务名） |
| 开源路径 | `oss_flink` / `oss_paimon` / `oss_fluss` | **三段都要填全**（`home`/`rest_endpoint`、`connector_jar`/`warehouse`、`home`/`bootstrap_servers`） |

只配开源栈也算就绪，不会因为"没填平台执行器"报缺口；反过来只配平台栈也一样。某条路配了一半，`env check` 会点名缺哪个键。

## CLI 缺能力时

先问要不要升级；拒绝升级再按 `governance/executor-arbitration.md` 评估有界回退。**不自动切换执行器**；版本号不是判据，帮助正文才是。
