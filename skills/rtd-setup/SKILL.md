---
name: rtd-setup
description: 初始化实时数开运行时（Codex 入口，等价于 /setup）
---

# rtd-setup（Codex 版 `/setup`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/setup.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-setup — 初始化实时数开运行时

在**项目**里（不是插件仓库里）执行。只做四件事，做完给你一份缺口清单。

## 第一步：建运行时目录

```
py -3 .rtd/engine/rtd.py setup --project <项目根>
```

引擎会建出 `.rtd/`（状态、证据、执行记录、快照四个子目录），并把 `.rtd/` 追加进项目 `.gitignore`。已经存在时不覆盖，只补缺的子目录。

## 第二步：生成配置模板

把 `templates/config.example.json` 复制成 `.rtd/config.json`（权限 0600），然后**你来填**：

| 键 | 填什么 | 不填的后果 |
| --- | --- | --- |
| `executors.cli.cmd` | 平台 CLI 可执行名 | 研发主流程走不了，只能走 MCP 分支 |
| `executors.cli.install_hint` | 该 CLI 的安装方式 | 缺 CLI 时无法按仲裁规则征询安装 |
| `executors.mcp_dev` / `mcp_ops` / `mcp_asset` / `mcp_engine` | 各域 MCP 服务名 | 对应域的能力不可用，回退路径不成立 |
| `executors.storage.*` | 存储侧取证工具名 | 存储症状分支止步 |
| `limits.*` | 预算与轮询节奏 | 巡检/轮询按内置保守默认值，并在报告里标注"用默认值" |

**不要**把真实名称写进任何仓库文件；写进配置就是唯一落点。

## 第三步：探测执行器（只读）

```
py -3 .rtd/engine/rtd.py env check --json
```

每个执行器只做一次**针对明确目标**的只读探测，结果分三档：`配置存在` / `认证完成` / `当前会话可调用`。

只有第三档算可用。第一档就宣布"接好了"是错的——`governance/mcp-setup.md` 里写了为什么。

## 第四步：输出缺口清单

```
py -3 .rtd/engine/rtd.py env check          # 缺口清单就是它的输出（含 limits 缺项提示）
```

格式固定：每个缺口写**缺什么、影响哪个阶段、下一步怎么补**。三项都齐了就打印 `READY`，可以进 `/rtd-dev`。

> 注意：引擎没有 `setup --report` 这种写法（早期文档里写错过，已被校验器第 4 项拦住）。缺口一律看 `env check`。

## 收尾要说的话

- 说清哪些执行器处于哪一档，**不要**把"配置存在"说成"可以使用"；
- 说清 `.rtd/config.json` 的权限与"不进仓库"的约定；
- 探测失败时给真实错误原文，不要转述成"网络问题"。
