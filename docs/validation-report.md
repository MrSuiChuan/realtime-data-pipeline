# 验证记录

本文件记录"这个包凭什么说自己可信"，以及**哪些东西现在还没被验证**。维护者每完成一轮核实就往这里追加一段，不要覆盖历史。

## 0. 记录规范

每条记录写清三件事：**谁**（维护者）、**何时**、**用什么方法**核实了什么。没做过的事不写进来；拿不准的写成"未验证"。

---

## 2026-09-21 · 骨架阶段（0.1.0 未发布）

**核实人**：维护者（本机）

**已核实**

| 项 | 方法 | 结果 |
| --- | --- | --- |
| 双宿主清单可解析、版本单源 | `tools/validate_plugin.py` 第 5 项 + `tests/test_repo_invariants.py` | 通过（claude `0.1.0`，codex 带 `+codex.<token>` 后缀） |
| 脱敏词表零命中 | 第 7 项全仓扫描（排除 `plan.raw.md` 与词表自身） | 通过 |
| 链接目标存在 | 第 2 项，全包 Markdown 相对链接 | 通过 |
| capability-matrix 引用一致 | 第 3 项 | 通过（首轮曾抓到一处指向不存在文件的引用，已修） |

**未验证（不要当成已验证）**

| 项 | 现状 | 说明 |
| --- | --- | --- |
| 真实平台连通 | 未接 | 本机没有配置任何执行器；`mcp-setup.md` 的三种状态里只到"配置存在"这一步都还没到 |
| 引擎状态机 | 未实现 | 第十四章的状态机还在 Q7 |
| 巡检评分阈值 | 未校准 | 相关脚本尚未移植；阈值是待校准的技术启发式，**不是**官方健康模型，禁止当 SLA 用 |
| 工作流行为回归 | 未做 | 需要 evals（Q8）才能真正跑 |

**边界声明（沿袭既有诚实口径）**

1. 本包**没有**携带任何平台的专有测试集，因此**不可由此包复现**任何"249 项单测通过"之类的结论；此类结论若出现，必须注明"仅在原维护者环境验证"。
2. 本包不含真实平台名、命令名与服务名：脱敏是**构建时**约束，不是运行时的能力声明。能不能用，取决于使用者本地 `.rtd/config.json` 填了什么。

---

## 2026-09-21 · 引擎、hook 与工作流落地（0.1.0 未发布）

**核实人**：维护者（本机）

**已核实**

| 项 | 方法 | 结果 |
| --- | --- | --- |
| 引擎门控语义 | `tests/test_engine.py`（10 条） | 通过：回读类门拒绝确认顶替；证据缺字段/非 JSON/空文件拒收；门未满足不能跳阶段；确认类门要求原话，恢复点拒绝"当前时间" |
| 证据防篡改 | 同上（改动证据文件后自检） | 通过：`verify` 报哈希不符 |
| 跨会话对账 | 同上 | 通过：状态与回读不一致时拒绝续跑并列出差异，且**不覆盖**状态 |
| hook 硬门 | `tests/test_hooks.py`（7 条） | 通过：证据目录直写、无确认的 `--yes`、无确认的高风险动词均被拦；普通命令放行；超过 30 分钟的旧确认不算数 |
| hook 宿主协议 | 手工把 JSON 喂给 `hooks/pretooluse.py` / `sessionstart.py` | 通过：三例阻断 + 一例放行 + SessionStart 阶段提醒，输出 JSON 可被宿主解析 |
| 端到端链路 | 临时项目里跑 `setup → advance → evidence add → gate set → advance → verify` | 通过：`.rtd/` 六类目录生成、引擎自拷贝到 `.rtd/engine/`、状态与门控记录齐全 |
| 静态校验八项 | `tools/validate_plugin.py` | 通过（首轮抓到三处真缺陷：能力矩阵悬空引用、执行器契约里的业务叙事词、工作流里内联命令串——均已修，未放宽检查） |

**未验证（不要当成已验证）**

| 项 | 现状 | 说明 |
| --- | --- | --- |
| 真实平台连通 | 未接 | 本机没配任何执行器；`env check` 只能判到"配置是否存在" |
| 真实平台的门控链路 | 未做 | 只有合成证据跑通；真实回执的字段名需要联调后回填 `executors/contracts-*.md` |
| 巡检评分 | 未实现 | 评分脚本与阈值校准还没做（对应 plan 的 Q8 之后） |
| evals 语义判分 | 未自动化 | 跑分器（`tools/run_evals.py`）已能校验结构、导出评分表、汇总得分；**语义判分仍由人或 Agent 做**，不要把"评分表导出成功"当成"行为已回归" |

**后续补充（同日）**

| 项 | 方法 | 结果 |
| --- | --- | --- |
| evals 结构校验 | `tools/run_evals.py --check` | 通过：5 套 21 条用例，缺字段/空 expectations/重复 prompt 都会被拦 |
| 跑分器自测 | `tests/test_evals_runner.py`（5 条） | 通过：结构问题能抓到；`--score` 对缺评分与"判失败没写理由"报错 |
| 评分表导出 | `--export` | 通过：每条用例都有独立小节与判定点清单 |

**第二轮修复后的补充（同日更晚）**

| 项 | 方法 | 结果 |
| --- | --- | --- |
| 巡检评分脚本 | `tests/test_score_inspection.py`（6 条） | 通过：能出 report.md + score.json；输出目录已存在、写在插件仓库内、快照有重复键、快照版本不对，四类都被拒 |
| 评分口径 | 读 `tools/score_inspection.py` 头部契约与 `score_of` | 覆盖不足时分数被夹到 74 上限并标"已观测风险暂评分"；信号缺失记 unknown 不扣分不判正常 |
| 文档与引擎对账 | `validate_plugin` 第 4 项 + `tests/test_repo_invariants.py::test_engine_invocations_in_docs_match_the_engine` | 通过：修正 `commands/setup.md` 里不存在的 `setup --report`；新增检查会拦住"文档写了引擎不认的子命令/参数" |
| 阈值校准 | —— | **未做**：脚本里的分档是待校准的技术启发式，需真实正常/故障窗口才能定（见台账 RTD-023） |

**第二轮收尾（RTD-025/026/027）**

| 项 | 方法 | 结果 |
| --- | --- | --- |
| 证据绑对象身份 | `tests/test_engine.py::test_evidence_expires_when_object_identity_changes` | 通过：换成另一个文件级 ID（版本相同）后，旧编译回执设门被拒 |
| 非顺序推进要理由 | `tests/test_engine.py::test_non_sequential_advance_requires_reason` | 通过：跳阶段与回跳在空理由时被拒，有理由时放行并落记录 |
| 运行时记插件版本 | `tests/test_engine.py::test_setup_records_plugin_version` | 通过：`_state.json` 的 engine 段含哈希与插件版本 |
| 台账完成度 | `awr intake inspect --source-sha <提交>` | `source_completed 18 / verified_completed 18`，无 completion_unverified |

**能力边界（写在引擎里，也写在这里）**

引擎能验证证据的**存在、哈希、必填字段、时间与类型匹配**；它**不能**证明那份原始输出真的来自平台。伪造 `tool`/`command`/`observed_at` 是人要负责的边界，不是引擎能兜住的。

---

## 2026-09-23 · hook 在两个宿主的实测（RTD-014）

**核实人**：维护者（本机）

| 项 | 方法 | 结果 |
| --- | --- | --- |
| Claude Code 装载 | `claude plugin marketplace add` + `install`，再 `claude plugin details` | 通过：组件清单列出 `Hooks (2) PreToolUse, SessionStart` |
| Claude Code 拦截 | 非交互会话里让模型往证据目录写一个探针文件 | **被拒**，文件未创建，拒绝原因来自本插件的 `evidence_write` 门；对照组（写系统临时目录）正常执行 |
| Codex 装载 | 个人 marketplace 加条目 + `codex plugin add`，看 `codex plugin list` | 通过：`installed, enabled` |
| Codex 信任 | 看 `~/.codex/config.toml` 的 `[hooks.state]` | 通过：出现本插件的 `pre_tool_use:0:0` 与 `session_start:0:0` 两条信任记录 |
| Codex 拦截 | 在已加载插件的会话里执行一条针对证据目录的写入命令 | **被拒**：`Command blocked by PreToolUse hook: [realtime-data-plugin:evidence_write] …` |
| `codex exec` 行为 | 用已信任的姊妹插件做对照：在 exec 模式下写它 guard 的运行时目录 | 写入**成功** → **`codex exec` 不加载插件 hook**，门禁只覆盖交互式会话 |

**踩过并已修的坑（两条）**

1. **Codex 的 hooks 文件顶层必须包一层 `hooks`**：我一度把它去掉，宿主识别到 0 个钩子——既不报错也不弹信任提示（这就是"别的插件都弹了、它不弹"的原因）。现在校验器第 1 项会拦：缺包裹、事件名不是 PascalCase、命令条目缺 `command` 都会红。
2. **门会连带拦住"提到受保护路径的文档与补丁"**：写这份记录时，补丁正文里出现证据目录字面量就被自己的门拒了一次。属于可接受的假阳性（改措辞即可绕开），但也说明：**门拦的是字符串，不区分"要写文件"还是"只是提到"**。

**未验证**：非交互/脚本化调用（`codex exec`、CI 里直接跑 shell）不受门控，任何自动化流程要自己兜住写操作。

---

## 待裁决：`hooks` 字段与官方校验器的冲突

**事实（两边都核实过）**

1. `plugin-creator` 附带的 `scripts/validate_plugin.py` 的 `allowed_keys` **不含 `hooks`**，所以本仓库 `.codex-plugin/plugin.json` 会被它判为不通过；SKILL.md 也写着"omit unsupported fields, including `hooks`"。
2. 但同一个 skill 的 `references/plugin-json-spec.md` 把 `hooks` 列为**合法的顶层字段**（"hooks (string): Hook config path"）。
3. 已安装并正在使用的 `data-development-plugin` 的清单里就带 `hooks`，而且**宿主 ingest 后的缓存副本原样保留了该字段**（比对 `~/.codex/plugins/cache/personal/data-development-plugin/<ver>/.codex-plugin/plugin.json` 与仓库副本，两边一致，未被剥离）。

**本仓库当前选择**：保留 `hooks`（去掉它等于放弃 PreToolUse 硬门；合并前先确认宿主真的读了它）。

**需要用户裁决**：若确认宿主不读该字段，则改为"hooks 只在 Claude Code 侧生效"，并把 Codex 侧的门禁降级为提示词层，同时在 README 与 SECURITY 里如实写明强度差异。
