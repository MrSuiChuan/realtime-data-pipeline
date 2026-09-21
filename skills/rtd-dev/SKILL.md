---
name: rtd-dev
description: 实时任务研发主流程（Codex 入口，等价于 /dev）
---

# rtd-dev（Codex 版 `/dev`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/dev.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-dev — 实时任务研发主流程

流程见 `workflows/runbook-dev.md`（场景一有 SQL / 场景二只有需求；迁移走 `/rtd-migrate`）。

## 阶段与门控

```
design（refs_published）→ build（compile_ok）→ debug（debug_confirmed）
→ configure（sla_decided）→ submit（submit_ok）→ publish（publish_ok）→ start（走 lifecycle）
```

每个门都由引擎按证据开：

```
py -3 .rtd/engine/rtd.py evidence add --kind refs_readback --from refs.json --tool "<执行器>" --command "<真实命令>"
py -3 .rtd/engine/rtd.py gate set --name refs_published --evidence <id>
py -3 .rtd/engine/rtd.py advance --phase build --reason "引用元表已确认发布"
```

## 三条最容易做错的

1. **引用表只认已发布版本**：开发版存在不算可用；搜索是模糊匹配，必须按名称完全相等确认；
2. **调试成功 ≠ 业务正确**：输出为空要查流量、过滤与窗口，别默认推进；
3. **发布要独立确认**：提交成功不含发布信息；校验待人工确认时原样返回链接并停止，人工完成后重查同一次校验，不盲重提。

## 完成判据

发布完成（是否启动另说，启动走 `/rtd-lifecycle` 的门）。每阶段返回状态、关键错误与**本次真实获得的平台链接**。
