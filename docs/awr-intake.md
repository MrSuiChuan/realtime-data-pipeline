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

## 2026-09-22 凌晨：第二轮修复收口与验证锚点

第二轮修复（RTD-016 ～ RTD-028）后，台账 28 项，其中 **21 项已完成并在 `ac3ac06` 上全部通过 SHA 校验**：

```
awr intake inspect --project . --source-sha ac3ac06 --json
→ completed 21 / verified_completed 21 / completion_unverified 0
```

### 一个必须知道的固有成本：验证是"按提交"的

AWR 的完成校验绑定具体提交。含义有三条：

1. **跑绑定的那一轮之后，任何新提交都会让已完成项重新变成未验证**——不是回退，是"这一版还没验过"；
2. 报告因此按提交短 SHA 命名（`docs/reports/rtd-016-completion-<sha>.json`），历史报告不覆盖；代价是每轮 +21 个文件，已经 40+；
3. 查询时**必须显式带 SHA**，不带就只看得到状态声明而不是验证结论：

```bash
awr intake inspect --project . --source-sha <代码提交> --json
```

当前锚点约定：**校验锚定在代码提交**（`ac3ac06`）；其后的台账/报告提交（`7f07a5c`）只做记录，不重复绑定。这条约定与"报告目录要不要收缩"一起记在 RTD-028 里，等策略定了再动结构。

### RTD-028 定案（2026-09-22）

- **锚点策略**：验证锚定在代码提交；只写台账/报告的提交不重新锚定。核对方式固定为带 `--source-sha` 的 inspect（README 与 `docs/reports/README.md` 都写了）。
- **保留策略**：报告全量保留，不做轮次收缩——单份约 2 KB，删掉会让历史提交的验证失去可复核性。目录结构保持扁平，命名 `<工作项>-completion-<短SHA>.json`。
- **可维护性**：新增 `tools/awr_reports.py`，一条命令看每个工作项最新一轮是哪个提交（`--json` 给机器读，`--limit N` 只看最近几轮）。

## 2026-09-30：完成通道再次被卡住（quoted scalar marker mismatch）

这一轮想把 RTD-038 ~ RTD-058 按流程置完成，**卡在写回这一步**。现场如下（可复现）：

```
$ awr work progress RTD-011 --session <sid> --reason ... --expected-revision <rev> --json
{"code":"proposal_required",
 "error":{"details":{"proposal_id":"01M3S61MEC10B8DP0955QPY7BN",
                     "reason":"quoted scalar marker mismatch"}}}

$ awr proposal apply <proposal_id> --actor codex --reason ... --expected-revision <rev> --json
（同样的 proposal_required / quoted scalar marker mismatch）
```

要点：

* **不是某个条目的问题**：`RTD-011` 是完全没动过的旧条目，一样报同一个错；
* **不是生命周期动作的问题**：连 `work progress` 这种最简单的写回也走同一条路；
* **不是行尾的问题**：实测 `work-ledger.yaml` 是纯 LF（CRLF 计数 0）；
* **证据侧是好的**：`evidence add` 与 `work prepare-completion` 都能通过，验收报告也照常落到
  `docs/reports/`——**卡住的只有"把 status 写回 YAML"这一步**。

所以流程是：**证据能登记，状态写不回。** 结果是工作项停在 `in_progress`，
而它对应的验收报告与证据记录已经在账上（按提交 SHA 绑定）。

顺带记住一条流程细节：`work complete` 生成的提案**必须在发起它的会话还活着的时候应用**。
先 `session end` 再 `proposal apply` 会报 `InvalidTransition: session ... is ended`——
这不是缓存问题，重开会话也救不回来，只能重做一次 `work complete` 生成新提案。

### 根因与修法（2026-10-01 查清并修复）

**根因是块标量，不是引号风格。** AWR 的 `yaml-ledger-v1` 改写器**按行找映射冒号**，
而 `key: |` 块标量的**续行没有冒号**，被它当成坏映射 → 整份账本任何一次写回都失败。

定位过程（每一步都可复现）：

1. **最小账本能写**：一个只有 `id/title/status/acceptance` 的账本，`work progress` 直接成功
   → 排除"环境不通"；
2. **带引号键也能写**：把旧条目那种 `"evidence"` / `"verification"` / `"blocker"` 搬进最小项目，
   同样成功 → 排除引号风格；
3. **逐条搬入最小项目单测**，报错变具体：
   * `RTD-038` → `YAML marker outside source`
   * `RTD-043` → `missing YAML mapping colon`
   两条都指向同一个写法：它们的 `summary` 用的是多行块标量；
4. **压成单行后立刻变 `proposal_recorded`** → 根因确认。

修法：机械压平账本里的 **23 处**块标量（续行用空格连接，只改写法不改语义），
重新 `source reindex`。修完当场验证：本轮 18 个工作项按代码提交 `7fed5e5` 绑定验收报告并置完成，
`awr intake inspect --source-sha 7fed5e5` 从 `verified_completed = 0` 变成 **19**。

**纪律**：以后往账本里写 `summary`/`next_action` 等字段，**一律用单行标量**，
不要用 `|` 块标量——这不是风格偏好，是写回通道的硬约束。

### 另一个坑：claim 会被测试会话占住

调试期间起的会话如果没有 `session end`，会一直持有该工作项的 claim，
下一次写回报 `ClaimConflict: another session holds this work`。
处置：`awr session list` 找出 `active` 的会话，逐个 `session end --outcome interrupted` 释放后再重试。

## 2026-10-07：收口"无法验证"的工作项（用 cancel，不用 complete）

本机没有平台环境，RTD-011 与挂在它下面的四个项永远拿不到证据。收口方式选了 `work cancel` 而不是
`work complete`——**complete 的语义是"做完了、证据齐"，这五项没有证据**，用 complete 等于把没做的事说成做完了。
cancel 是终止态，写清原因即可；`awr work reopen <id>` 可以随时重新打开。

三条实测出来的限制，下次直接用：

1. **`cancel` 只认 `--reason` 与 `--next-action`**：带 `--blocker` 会报
   `field blocker is not authorized by this work action`，带 `--summary` 报同类的 summary 版本——
   阻塞与现状只能并进 `--reason` 里，别指望有专门的字段。
2. **`cancel` 和 `complete` 一样走提案通道**：直接调用返回的是 `proposal_required` + `proposal_id`，
   还要 `proposal submit → approve → apply` 三步，而且**必须在发起它的会话还活着时应用**
   （会话先结束会报 `InvalidTransition: session ... is ended`）。
3. **重复收口是幂等的**：已经 cancelled 的项再取消一次会报
   `InvalidTransition: cannot Cancel work with source state Cancelled`——
   看到这条说明**已经是目标状态**，不是失败。
