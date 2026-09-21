---
name: rtd-diagnose
description: 异常诊断（Codex 入口，等价于 /diagnose）
---

# rtd-diagnose（Codex 版 `/diagnose`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/diagnose.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-diagnose — 异常诊断

流程见 `workflows/runbook-diagnosis.md`。**诊断结束不自动变更、不自愈。**

## 循环

明确症状与窗口 → 平台侧定位异常任务 → 引擎侧按症状取最少证据 → 收窄到算子/子任务/实例 → 核反证 → 出结论。

每次调用都要能回答："它支持或反驳了哪条假设？"

## 四条最容易越界的地方

1. **引擎侧只读**：平台工具坏了也不改走引擎侧去停作业；
2. **RUNNING ≠ 健康**，空事件查询 ≠ 健康证明；
3. 日志/指标必须带窗口与基线；时间相关 ≠ 因果；
4. 存储分支：凭据不落聊天与报告；配额有余量只反驳"配额耗尽"这一条假设。

## 交付

四要素 + 四级结论（已确认 / 较可能 / 已排除 / 未决），每级附支持与反证；核心结论写在回复里。要动手就转 `runbook-lifecycle.md` 并走确认门。
