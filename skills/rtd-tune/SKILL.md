---
name: rtd-tune
description: 单算子与运行参数调整（Codex 入口，等价于 /tune）
---

# rtd-tune（Codex 版 `/tune`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/tune.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-tune — 单算子与运行参数调整

流程见 `workflows/runbook-tuning.md`；生效方式与限制见 `workflows/version-effect-matrix.md`。

## 八步

澄清目标（"优化一下"→ 先诊断）→ 取完整快照 → 只改目标字段（按稳定 ID，不按数组下标）→ 评估生效方式与风险 → 提案确认 → 重读后保存 → 部署并验证 → 观察效果。

## 四条硬约束

1. "只改一个节点"是意图，请求仍须**全量**结构；
2. 同链发散并发**必须完整重启**，热更新不适用；
3. 运行参数写后要重新查询核实；返回的前后值不是两份独立快照；
4. **无并发保护（无 CAS）**：读后写有竞态，发现他人变更就停止旧提交。

## 中间态是合法的

"已部署，运行差异待核验"可以如实写；只有确认"应生效而未生效"才判未生效。不循环重复同一个操作。
