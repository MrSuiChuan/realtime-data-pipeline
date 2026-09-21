# AWR 接入记录

用 AWR（Agent Work Runtime）接管本项目的工作状态。权威源在 `.awr/intake/`，运行时状态（`state.db`）不进仓库。

## 怎么接的

```bash
awr init --project . --json                 # 先看源映射，不写任何东西
awr init --accept --project . --goal "…"     # 确认后初始化
awr source reindex --project .              # 改过权威源之后必须重跑
awr intake inspect --project . --json       # 看状态、缺口与有序修复动作
awr ready --project .                       # 看"现在能做"的工作项
```

三个权威源：

| 源 | 文件 | 作用 |
| --- | --- | --- |
| goal | `.awr/intake/GOALS.md` | 目标与成功标准（**只保留一个一级标题**） |
| ledger | `.awr/intake/work-ledger.yaml` | 16 个工作项（RTD-000…015），带验收、下一步、依赖与证据引用 |
| plan | `plan.md` + `README.md` | 设计稿与仓库说明（只读支撑） |

## 当前状态（2026-09-21）

```
state: ready
counts: completed 10 / planned 4 / ready 2
executable_work: RTD-011, RTD-012, RTD-014
gaps: completion_unverified ×10, dependency_not_completed ×4
```

## AWR 抓出来的问题（都是真的）

1. **完成声明未绑定验收报告**（`completion_unverified` ×10）：`source_completed=10` 但 `verified_completed=0`。AWR 要求把每条验收标准绑定到**指定 source SHA** 的通过报告；本项目**还不是 git 仓库**，没有 commit SHA 可绑，所以 `locally_verified` 级证据一律被拒（实测报 `EvidenceMissing: missing bindings: source_sha`）。→ 先 `git init` 并提交一次，证据才能升到"本地已验证"。
2. **依赖阻塞 ×4**：RTD-009 / RTD-010 / RTD-015 依赖 RTD-011（真实执行器联调），联调没做就推不动。
3. **接入时的两个源错误**（已修）：GOALS.md 里多写两个 `##` 标题，被 markdown 适配器当成两个"野目标"；工作项的 `goal:` 用了短 id，没对上 Markdown 目标的完整键。AWR 的 `goal_unconfirmed` / `work_goal_unresolved` 把这两条都指了出来。

## 下一步（按可执行性排序）

| 项 | 谁做 | 说明 |
| --- | --- | --- |
| RTD-014 裁决 hooks 是否在 Codex 生效 | 用户一次操作 | 装进 Codex 触发一次门控，决定硬门是否成立 |
| RTD-012 巡检评分脚本 | 可继续做 | 先定快照输入契约与报告输出契约 |
| RTD-011 真实执行器联调 | 需要环境 | 完成后才能回填 RTD-009/010 |
| 把证据写入接进 CI | 可继续做 | 每轮跑完自动登记一条 evidence，完成声明才有机器可查的绑定 |

## 已知限制

- **MCP 已指定到本项目**（2026-09-21）：`~/.codex/config.toml` 的 `[mcp_servers.awr] args` 改为 `--project …\realtime-data-plugin`，原值（指向 `.local\demo`）与备份写在配置注释与 `config.toml.bak-awr-repoint`。**Codex 里已有的 MCP 进程仍持旧参数，重启 Codex 后才生效**；重启前用 CLI 的 `awr --project .` 一样能干活。
  验证方式：用新参数起一次 `awr-mcp.exe --project <本仓库>` 并调用 `awr_project_status`，返回 `project=realtime-data-plugin / state=ready / ready_count=3 / work_total=16`。
  多项目需要另一种配置：`awr-mcp --registry <注册表>` 起 HTTP 端点，单项目 stdio 一次只能服务一个仓库。
- AWR 不执行任何命令，也不证明内容真伪：它检查的是**声明、引用与绑定**是否自洽。
