---
name: rtd-discover
description: 定位与状态快查（Codex 入口，等价于 /discover）
---

# rtd-discover（Codex 版 `/discover`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/discover.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-discover — 定位与状态快查

流程见 `workflows/runbook-discovery.md`。只定位、只看状态，**不自动升级**成巡检或诊断。

## 做什么

1. 把用户给的线索归一（名称 / ID / 实例 / 链接 / 项目）；
2. 链接先按 `knowledge/link-parsing.md` 解析；解析不出就保留缺口，不猜；
3. 唯一定位（搜索要翻完页）；多候选列出来让用户选，不默认第一个；
4. 展开拓扑与任务结构，分层保存 ID；
5. 一句话回报状态，格式按 `governance/response-contracts.md` 的"状态快查"。

## 记到运行时

```
py -3 .rtd/engine/rtd.py object set --name "<对象名>" --file-id "<文件级 ID>" --source "ops search"
py -3 .rtd/engine/rtd.py status
```

## 不许做

- 不许用"首屏没搜到"结论"不存在"；
- 不许把一个候选默认成答案；
- 不许顺手做诊断或变更（用户没要求）。
