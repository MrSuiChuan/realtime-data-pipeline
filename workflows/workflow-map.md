# 工作流衔接总图

```
                 ┌─ 场景一（有 SQL）─────────────┐
用户请求 ──路由── ├─ 场景二（需求）→ 设计 → SQL ──┤→ 前置检查 →（表缺失）→ metatable ─┐
                 └─ 场景三（迁移）→ 定位 → 参数 ──┘   → 项目 / 目录 / 渲染 / 创建 / 写入 ←┘
                          → 编译（权限墙 → 环境 / 权限）→ 调试 → 配置（SLA / 备表缺失 → metatable）
                          → 提交 → 发布（待人工确认时停下来等）→ 启动（走 lifecycle 的部署契约）

运维域：discovery（快查）→ inspection（巡检）⇄ diagnosis（诊断）→ tuning / lifecycle（变更，经确认）
             └────────── 知识 / FAQ 只作参考，一切变更回到右侧的门禁通道 ──────────┘
```

## 阶段与门控（引擎视角）

```
discover → design → build → debug → configure → submit → publish → start
```

| 阶段 | 门控键 | 类型 |
| --- | --- | --- |
| design | `refs_published` | 平台回读 |
| build | `compile_ok` | 平台回读 |
| debug | `debug_confirmed` | 当次确认 |
| configure | `sla_decided` | 当次确认 |
| submit | `submit_ok` | 平台回读 |
| publish | `publish_ok` | 平台回读 |
| start | `start_confirmed` + `source_stopped` + `reset_time` | 当次确认（三项独立） |

## 从任何阶段都能做的事

| 想做 | 去哪 |
| --- | --- |
| 看现在在哪、缺什么 | `/rtd-status` |
| 跨会话接着干 | `/rtd-status` → 回读平台 → `rtd.py resume --observed …` |
| 只改一张表、补一个测试、查个状态 | 直接进对应 runbook，不必跑整条流水线 |
| 环境/执行器有问题 | `runbook-environment.md` |
