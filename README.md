# realtime-data-plugin

把实时数据任务的研发工艺翻成**状态机 + 硬门控**：AI 在门内自己干活，阶段出口只认机器证据。

## 它解决什么问题

实时任务开发的坑不在"会不会写 SQL"，而在三件事上：

1. **证据不实**：编译"看起来过了"、发布"应该成功了"、调试"没报错"，然后线上发现表没数据；
2. **确认失效**：一次同意被当成一路放行，启动、回刷、下线这些改线上状态的动作没有当次确认；
3. **状态丢失**：换个会话接着干，对象 ID、版本、追踪 ID 全凭记忆，重发一次写操作就是事故。

本插件把这三件事变成机制：阶段出口有门控键、门控键只能由引擎按证据写入、证据落盘可核验、续跑先回读平台真实状态。

## 三层结构

| 层 | 目录 | 作用 |
| --- | --- | --- |
| 规制层 | `governance/` | 安全宪法（门禁与只读边界）、执行器仲裁、身份与时间、输出契约、反例库、能力矩阵 |
| 工作流层 | `workflows/` | 十份 runbook：定位、研发、迁移、元表、启停、巡检、诊断、调参、环境、衔接总图 |
| 执行器层 | `executors/` + 项目级 `.rtd/config.json` | 命令与工具契约；真实命令名/MCP 服务名只在配置里 |

## 执行器与脱敏

仓库内**不含任何平台专有名**。平台 CLI 命令名、各域 MCP 服务名、存储分支工具名，以及巡检预算、轮询节奏等限额，全部从项目级 `.rtd/config.json` 读取（该文件不进仓库、不进发布包，权限 0600）。

配置缺项时的行为是**报缺口并停**：不猜命令名、不自动安装、不自动切换到另一个执行器。

仓库里同样**不含脱敏词表本身**：`tools/desensitize_terms.txt` 写的是要拦的真实内部代号，随仓库公开等于公开要藏的名字——所以它只在本地（已 gitignore），CI 用仓库 secret `RTD_DESENSITIZE_TERMS` 注入；两边都没有时第 7 项显示 `SKIP` 并写明原因。格式见 `tools/desensitize_terms.example.txt`。

## 安装

两个宿主共用同一套引擎、工作流与 hook 脚本，装哪个都行（也可以都装）。

```bash
# Codex
codex plugin marketplace add <本仓库路径>
codex plugin add realtime-data-plugin@personal

# Claude Code（仓库自带 .claude-plugin/marketplace.json）
claude plugin marketplace add <本仓库路径>
claude plugin install realtime-data-plugin@realtime-data-plugin
```

**装完必须开新会话**：插件列表在会话启动时加载，当前会话里看不到新装的插件。首次加载时宿主会问是否信任这个插件的 hook——**要信任**，否则硬门不生效（原因与核实方法见 `docs/host-hooks.md`）。

## 快速开始

```bash
# 1) 在项目里初始化运行时并填执行器配置
/rtd-setup                 # Claude Code；Codex 侧入口是技能 rtd-setup

# 2) 开工：从需求到上线，阶段出口有门控
/rtd-dev "把这两张实时表做成一条宽表任务，10 秒聚合"
```

初始化会创建 `<项目>/.rtd/`（状态、证据、执行记录）并生成 `config.json` 模板；填好执行器后 `rtd-status` 会列出当前还缺哪一项。

执行器有两条路，选一条配全即可：**平台路径**（平台 CLI + 各域 MCP）或**开源路径**（Flink / Paimon / Fluss，三段 `oss_*` 都要填）。`rtd-env` 分别判定，不会拿另一条路的要求来报缺口。

## 要求

- Python 3.11+（引擎、校验器与工具只用标准库；跑测试需要 pytest）；
- Windows / macOS / Linux 均可；hook 的启动器用 `tools/adapt_hooks.py` 按平台适配；
- 不需要任何平台凭据也能启动：配置为空时引擎报缺口并停下，不替你猜。

## 范围与边界（先说清不做什么）

| 做 | 不做 |
| --- | --- |
| 阶段状态机与门控键（证据 / 当次确认两类，不可互替） | 不内置任何平台的命令名与服务名（走项目级配置） |
| 证据账本（哈希可验）、执行记录、跨会话对账 | 不替你做线上变更；写操作都要当次确认 |
| 十份 runbook 与执行器契约 | 不打包平台专有的 schema 快照与内部测试集 |
| 开源栈（Flink / Paimon / Fluss）已本地实测 | 平台路径（平台 CLI / 各域 MCP）**未经真实环境验证**，按"未验证"呈现 |

## 文档索引

| 文档 | 内容 |
| --- | --- |
| `plan.md` | 设计源（脱敏版）：融合判断、五处关键合并、构建顺序 |
| `docs/host-hooks.md` | 两个宿主里 hook 的实测记录：什么生效、什么不生效、怎么核实 |
| `docs/oss-lab.md` | 本地开源栈实验：Flink / Paimon / Fluss 的安装、跑通过程与踩过的坑 |
| `docs/reports/README.md` | 台账验收报告的命名与锚点约定 |
| `docs/validation-report.md` | 验证记录：哪些已验证、哪些没有、边界在哪 |
| `governance/` `workflows/` `executors/` `datasources/` | 规制层、工作流层、执行器契约、数据源契约 |

## 现在到哪一步

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Q0 | 设计源与优化（`plan.md`） | ✅ |
| Q1 | 仓库骨架、双宿主清单、CI、脱敏词表 | ✅ |
| Q2 | 规制层 7 件（宪法/仲裁/身份时间/输出契约/反例库/接入/能力矩阵） | ✅ |
| Q3 | 工作流层：12 个命令入口 + 11 份工作流文档 | ✅ |
| Q4 | 执行器契约 5 份 + 配置层（`templates/config.example.json`） | ✅（schema 快照待回填） |
| Q5 | 数据源层：生命周期 + 类型槽位 | ✅（字段契约待回填） |
| Q6 | 知识层 3 件 + 出站路由映射 | ✅ |
| Q7 | 引擎 `engine/rtd.py` + hooks 硬门控 | ✅ |
| Q8 | evals 五组 + 八项静态校验 | ✅（定版与真实平台联调待做） |
| Q9 | 巡检评分脚本（离线出报告，不碰网络、不覆盖历史） | ✅（阈值待真实窗口校准） |

本地自检（当前全绿）：

```bash
py -3 tools/build_codex_surface.py --check   # 生成物与命令源一致
py -3 tools/adapt_hooks.py --check            # hook 启动器与平台一致
py -3 tools/validate_plugin.py .             # 八项静态校验（含脱敏扫描）
py -3 tests/test_engine.py                   # 引擎：门控/证据/阶段/续跑
py -3 tests/test_hooks.py                    # hook：三条硬规则的正负例
py -3 tests/test_score_inspection.py         # 巡检评分：出报告 + 拦住四类坏输入
py -3 tests/test_repo_invariants.py          # 仓库不变量
py -3 tools/awr_reports.py                    # 台账验收报告：每个工作项最新一轮是哪个提交
```

## 引擎怎么用（一步到位的样子）

```bash
py -3 <插件>/engine/rtd.py setup --project .        # 建 .rtd/，并把引擎自拷贝进去
py -3 .rtd/engine/rtd.py evidence add --kind compile_receipt --from compile.json \
  --tool "<执行器>" --command "<真实命令>"
py -3 .rtd/engine/rtd.py gate set --name compile_ok --evidence <evidence-id>
py -3 .rtd/engine/rtd.py advance --phase debug --reason "编译通过"
py -3 .rtd/engine/rtd.py status
```

门控键只有两种来源：**平台回读证据**（挂证据文件，验字段与哈希）和**当次确认原话**（`--user-confirm`）。两者不可互相顶替。

设计来源是 [plan.md](./plan.md)（脱敏版）。未脱敏原稿 `plan.raw.md` 带真实名称与替换对照表，**只在本地**，已在 `.gitignore` 里排除，别外发。

## License

MIT
