---
name: rtd-overview
description: 实时数开插件全貌（Codex 入口，等价于 /overview）
---

# rtd-overview（Codex 版 `/overview`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/overview.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-overview — 实时数开插件全貌

一句话：**实时任务开发的流水线，阶段出口只认机器证据。**

## 三层结构

| 层 | 目录 | 作用 |
| --- | --- | --- |
| 规制层 | `governance/` | 安全宪法（门禁 9 条 + 引擎只读边界 + unknown 语义）、执行器仲裁、身份与时间、输出契约、反例库、接入纪律、能力矩阵 |
| 工作流层 | `workflows/` | 十份 runbook：定位 / 研发 / 迁移 / 元表 / 启停 / 巡检 / 诊断 / 调参 / 环境 / 衔接总图 |
| 执行器层 | `executors/` + `.rtd/config.json` | 命令与工具契约；真实命令名、服务名、限额只在配置里 |

## 阶段与门控

```
discover → design → build → debug → configure → submit → publish → start
```

| 阶段 | 出口门控键 | 靠什么证据 |
| --- | --- | --- |
| design | `refs_published` | 引用元表已发布版本回读 |
| build | `compile_ok` | 编译终态回执 |
| debug | `debug_confirmed` | 调试模式 + 当次确认 |
| configure | `sla_decided` | SLA 决策（"跳过"也算决策） |
| submit | `submit_ok` | 提交终态 + 发布前校验状态 |
| publish | `publish_ok` | 发布终态 + 待发布对象回读 |
| start | `start_confirmed` + `source_stopped` + `reset_time` | 三项独立确认 |

门控键只能由引擎按证据写入。**没有例外，也没有"这次先跳过"。**

## 命令清单

| 命令 | 干什么 |
| --- | --- |
| `/rtd-setup` | 初始化项目运行时、生成配置模板、探测执行器 |
| `/rtd-status` | 看当前对象与阶段、下一个门控缺口 |
| `/rtd-discover` | 定位与状态快查 |
| `/rtd-dev` | 研发主流程（有 SQL / 只有需求） |
| `/rtd-migrate` | 实时 SQL 任务迁移 |
| `/rtd-metatable` | 元表查询/创建/发布 |
| `/rtd-lifecycle` | 启停、热更新、下线、取消部署 |
| `/rtd-inspect` | 单任务或批量巡检 |
| `/rtd-diagnose` | 异常诊断 |
| `/rtd-tune` | 单算子并发与运行参数调整 |
| `/rtd-env` | 执行器环境检查/安装/更新 |

编号越小越靠上游；`/rtd-dev` 是主流程，其余按需进入。

## 三条铁律

1. **写前确认**：任何改线上状态的动作都要当次确认，一次同意不传递到下一步；
2. **证据说话**：编译"看起来过了"不算过，要终态回执；接口返回成功最多是"已受理"；
3. **配置分离**：仓库里没有平台名，执行器与限额从 `.rtd/config.json` 读，缺项就停。
