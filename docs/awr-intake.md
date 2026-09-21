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

## 仓库与证据绑定（2026-09-21 晚）

| 项 | 值 |
| --- | --- |
| remote | `ssh://git@ssh.github.com:443/MrSuiChuan/realtime-data-plugin.git` |
| 首次提交 | `51f48bbaad35beb0c08281ca34377a7d49388f65`（main，已推送，远端与本地一致） |
| 入场文件 | 93 个；`plan.raw.md`、`.rtd/`、`.awr/state.db*`、`.awr/intake/inventory.json`、`.tmp/` 全部排除（`git check-ignore` 逐项验过） |
| 证据 | `evidence/rtd-013-evals-runner-verified`：level=`locally_verified`，source_sha=首次提交，scope=跑分器那 4 个路径 |
| 完成校验 | 仍 `verified_completed=0`（见下） |

## 卡点：手写 `completed` 会把自己锁死

实测走了一遍 AWR 的完成校验，卡在三处，**都是真实限制，不是配置没填**：

1. 我把 RTD-013 的 `status` 直接写成 `completed` → 之后 `awr session start --work RTD-013 --claim` 报
   `DependencyBlocked: source status is completed`：**已完成的工作不能再被认领去验证**。
2. `awr work reopen` 需要"绑定到该工作项"的会话，而不带 `--work` 的会话被拒：
   `work action session must be bound to the exact target work`。
3. 用绑定会话重开，提案生成了（`work.reopen`，已 approved），但 `proposal apply` 明确拒绝：
   `runtime-owned files cannot be source mutation targets` —— **账本放在 `.awr/intake/` 下，AWR 不许写自己运行时目录里的文件**。

**结论**：账本留在 `.awr/` 里，AWR 就只能读不能改；状态只能手写，而手写的 `completed` 永远拿不到 `verified_completed`（那 10 条 `completion_unverified` 就是这么来的）。

**修法（下一步，改动小但要动源映射）**：

1. 把账本与目标文件移出运行时目录，例如 `work-ledger.yaml`（仓库根）与 `GOALS.md`（仓库根或 `docs/`）；
2. `awr source configure` 替换源映射，再 `awr source reindex`；
3. 之后所有状态流转（progress / block / complete）都走 AWR 通道，`verified_completed` 才会动。

**另一条纪律**：新工作项**不要手写 `completed`**。留 `ready`/`in_progress`，用 `awr work complete` 绑定验收报告后再置完成——否则同样锁死。

## 2026-09-21 深夜：账本迁出 + 第二轮台账（RTD-016..022）

### 迁移

账本从 `.awr/intake/work-ledger.yaml` 迁到仓库根 `work-ledger.yaml`：

```bash
awr source relocate --project . --source <source-id> --to work-ledger.yaml --json   # 先拿 preview.fingerprint
awr source relocate --project . --source <source-id> --to work-ledger.yaml --expected-preview <fp> --accept
```

- `.awr/intake/GOALS.md` **迁不动**：AWR 明确回 `Unsupported: adapter keys depend on the old locator`。goal 是 Markdown 且对 AWR 只读，留在原地不影响写通道，因此保留；
- 旧副本 `.awr/intake/work-ledger.yaml` 已删除——两份账本并存会让人改错文件；
- `.awr/intake/project.toml` 保留（init 时的清单副本）。

### 又一个真限制：源文本里不能出现 `名字=值`

账本第一次改完 reindex 直接失败：

```
RuleViolation: sensitive content is not accepted; category=environment_dump
```

原因是我在 RTD-021 的摘要里写了 `CONFIRM_WINDOW_MINUTES=30` —— AWR 的敏感内容扫描把"大写名=值"当成环境变量转储。改成"确认窗口（30 分钟）"即可。

**规则**：写进权威源的文本里不要出现 `KEY=value` 形态（哪怕是常量名），否则整个源索引失败、项目状态退回 stale。

### 完成通道打通

RTD-016 / 017 / 018 / 019 / 022 已按完整流程置完成：验收报告落在 `docs/reports/<id>-completion.json`，证据绑定到提交 SHA，`awr work complete` 通过 propose→apply 写入账本。

查询口径：**完成校验是按 SHA 核的**，要看某个提交的验证情况必须显式带上：

```bash
awr intake inspect --project . --source-sha <commit> --json
```

当前（`1ed1d51`）：`completed 15 / verified_completed 5 / planned 6 / ready 2`；缺口 `completion_unverified 10 + dependency_not_completed 5`。
