---
name: rtd-resume
description: 跨会话续跑对账（Codex 入口，等价于 /resume）
---

# rtd-resume（Codex 版 `/resume`）

> 本文件由 `tools/build_codex_surface.py` 从 `commands/resume.md` 生成，请勿手改。
> 改流程请改命令源文件后重跑生成器。
> 命令里的 `py -3` 是 Windows 写法；macOS/Linux 换成 `python3`。

# rtd-resume — 跨会话续跑对账

换会话接着干之前**必须先对账**：状态文件说一套、平台上是另一套，直接接着做就是事故。

## 三步

1. 先看本地记了什么：

```
py -3 .rtd/engine/rtd.py status --json
```

2. 回读平台真实状态（对象、版本、运行态），写成 JSON 交给引擎对账：

```
py -3 .rtd/engine/rtd.py resume --observed observed.json
```

3. 对账通过才继续；有差异就按差异处理完再说。

## 规则

- **不一致就停**：引擎会列出字段级差异并拒绝标记为已续跑，**不会**用本地状态覆盖平台事实；
- 对账结果落进 `_state.json` 的 `last_resume`，报告里要写清"哪一刻、比对了哪些字段"；
- 不许用聊天记录当对账依据（宪法 unknown 语义 + §8.1）；
- 迁移场景另有约束：无法排除迁移来源时必须重新确认，不沿用上一会话的隐含记忆。

## 没有观测数据时

拿不到平台回读就**不要**跑 resume：如实说"无法对账，先做一次定位（`/rtd-discover`）"。
