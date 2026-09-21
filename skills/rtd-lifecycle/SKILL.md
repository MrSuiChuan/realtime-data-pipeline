---
name: rtd-lifecycle
description: 启停、热更新、下线、取消部署（Codex 入口，等价于 /lifecycle）
---

# rtd-lifecycle（Codex 版 `/lifecycle`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/lifecycle.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-lifecycle — 启停、热更新、下线、取消部署

流程见 `workflows/runbook-lifecycle.md`；版本语义见 `workflows/version-effect-matrix.md`。

## 前置三步（缺一即停）

1. 依赖预检：操作 / 配对进度 / 状态核验工具齐备——**即使用户已授权，工具不齐也停**；
2. 身份与时间：对象 / 实例 / 版本 / 时区；
3. 版本生效矩阵：快照来源、保存版本、生效方式、验证项。

## 展示六要素后再要确认

对象与环境 / 动作与版本 / 恢复点或重置时间 / SQL 与计划影响 / 预计停顿 / 风险与回退边界。

## 硬规则

| 规则 | 说明 |
| --- | --- |
| 确认不传递 | 安装同意、诊断结论、上一次启动的同意都不算本次确认 |
| 只提交一次 | 超时先查原状态，不重发；不编 ID |
| 终态成功 ≠ 完成 | 重读运行态核实际版本与参数；热更新还要回读物理结构 |
| 取消 ≠ 停止 | 取消部署是独立动作，不能条件取消 |
| 下线要证据 | 必须有"停止成功"的证据；"搜索不到"不算下线成功 |
