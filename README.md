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

执行器有两条路，选一条配全即可：**平台路径**（平台 CLI + 各域 MCP）或**开源路径**（`governance/oss-components.json` 里 tier 1/2 的组件，从 Flink / Kafka 到湖表格式）。
判定按**已开始的子集**：动过的组件必须配全，没动过的不算缺口——注册表越大越不该把"只配 Flink + Fluss"的人误报成没配齐。
`rtd-env` 分别判定两条路，不会拿另一条路的要求来报缺口。

## 开源栈工具（可选，但要连真集群时用它们）

`tools/oss_cli.py` 是 Flink / Fluss 的薄封装：配置读 `.rtd/config.json` 的 `executors.oss_*`，不接平台、不装依赖，只用标准库。

```bash
py -3 tools/oss_cli.py flink jobs                    # 列作业（Flink REST，原生 JSON）
py -3 tools/oss_cli.py flink status <jobId>          # 单作业状态
py -3 tools/oss_cli.py flink submit -f job.sql       # 提交 DDL/DML
py -3 tools/oss_cli.py fluss  sql -f fluss.sql       # Fluss 走 Flink 的 catalog（Fluss 没有 SQL 控制台）
py -3 tools/oss_cli.py evidence refs --table paimon.db_lab.t_orders --raw-dir raw/
```

三条要知道的：默认通道是 **SQL 客户端**（`--via gateway` 是备选，Gateway 在 Flink 2.2 上取结果不稳）；`evidence refs` 按表名前缀现建 `paimon.` / `fluss.` catalog，产出的 JSON 直接喂 `rtd.py evidence add --kind refs_readback`；**查失败一律记 `published: null` + 原因**，不会写成"没数据"。要连真集群时，CLI 得跑在能访问 `rest_endpoint` 的机器上。

实测记录（含失败案例）在 `docs/oss-lab.md` 第十二节。

`tools/oss_lab.py` 管**本机实验台**：装构件、起停组件、探就绪、跑冒烟。组件知识全部来自 `governance/oss-components.json`，本机设置（装在哪、用什么壳跑）放 `.rtd/lab.json`。

```bash
py -3 tools/oss_lab.py list                       # 登记了哪些组件、哪些构件还没配
py -3 tools/oss_lab.py plan oss_kafka             # 只看起停配方与冒烟步骤，不执行
py -3 tools/oss_lab.py start oss_kafka            # 起（有别的重型组件在跑会被拦）
py -3 tools/oss_lab.py smoke oss_kafka --count 3  # 建 topic → 灌 3 行 → 从头读回 3 行，原始输出落盘
py -3 tools/oss_lab.py stop  oss_kafka            # 停掉再上下一个
```

两条纪律写在工具里而不是文档里：**一次只起一个重型组件**（本机 7.7G 内存，同开两个失败现场分不清是谁的）；**读回 0 行不算通过**（冒烟把预期行数当硬条件，与退出码无关）。
组件维度的现状台账在 `docs/oss-component-ledger.md`。

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
| 开源栈 12 个组件已本地真跑（Flink / Paimon / Fluss / Kafka / Spark / Iceberg / Hudi / Delta / ClickHouse / Debezium / Pulsar / StarRocks） | 平台路径（平台 CLI / 各域 MCP）**未经真实环境验证**，按"未验证"呈现 |
| 组件注册表登记 13 个实时组件，逐个真跑、逐个填台账 | 没跑通的组件（当前只有 Doris：镜像拉取未完成）状态就写"未跑通"并附实测原因 |

## 文档索引

完整地图见 `docs/README.md`（按"我是谁"分：第一次来 / 想用起来 / 要参与开发 / 要发版 / 要看设计）。

| 文档 | 内容 |
| --- | --- |
| `plan.md` | 设计源（脱敏版）：融合判断、五处关键合并、构建顺序 |
| `docs/README.md` | 文档地图：不同角色从哪开始看 |
| `docs/glossary.md` | 术语表：门控键、证据、执行器、台账、tier 这些词到底指什么 |
| `docs/host-hooks.md` | 两个宿主里 hook 的实测记录：什么生效、什么不生效、怎么核实 |
| `docs/oss-lab.md` | 本地开源栈实验：Flink / Paimon / Fluss 的安装、跑通过程与踩过的坑 |
| `docs/oss-component-ledger.md` | 组件台账：13 个组件的角色、构件就绪判定、真跑到哪一步、下一步 |
| `docs/reports/README.md` | 台账验收报告的命名与锚点约定 |
| `docs/validation-report.md` | 验证记录：哪些已验证、哪些没有、边界在哪 |
| `docs/apache-readiness-audit.md` | 开源就绪审计：按 Apache 标准逐条自查，含未完成项 |
| `docs/release-process.md` | 发布流程与打包清单 |
| `docs/third-party-dependencies.md` | 第三方边界：仓库里有什么、实验台会下载什么、商标怎么用 |
| `governance/` `workflows/` `executors/` `datasources/` | 规制层、工作流层、执行器契约、数据源契约 |

## 参与与支持

| 你想 | 去哪 |
| --- | --- |
| 提缺陷 / 提能力 | `.github/ISSUE_TEMPLATE/` 里挑一个模板 |
| 配置接不上 | 用"配置求助"模板，附 `rtd.py env check` 的输出 |
| 贡献代码 | `CONTRIBUTING.md`（含 DCO 与评审流程） |
| 了解谁说了算 | `GOVERNANCE.md` |
| 报安全问题 | `SECURITY.md`（**不要开公开 issue**） |
| 参与讨论的底线 | `CODE_OF_CONDUCT.md` |

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
py -3 tests/test_oss_cli.py                  # 开源栈 CLI：真实输出回归 + 失败不冒充未发布
py -3 tests/test_oss_lab.py                  # 实验台：一次只起一个 + 读回 0 行不算通过
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

### 跑一遍应该看到什么（不依赖任何平台）

下面是在一个空项目里真跑的三步，输出是原样抓的（只把临时目录路径缩成 `<项目>`）：

```
$ py -3 <插件>/engine/rtd.py setup --project .
运行时：<项目>/.rtd
引擎版本：8a601d7262837eb5（已自拷贝到 .rtd/engine/）
新建：.rtd/_evidence、.rtd/_records、.rtd/_runs、.rtd/_snapshots、.rtd/_state.json、.rtd/config.json
已生成 config.json 模板——**接下来要你填执行器**（权限 0600，别提交）
已把 .rtd/ 追加进项目 .gitignore
缺口：
  - 两条路都没配置 —— 平台路径：至少把 executors.cli.cmd（或某个 mcp_* 服务名）填上；或 开源路径：按 governance/oss-components.json 里 tier 1/2 组件的 required_keys 配（动过哪个就必须配全哪个，没动过的不算缺口）

$ py -3 .rtd/engine/rtd.py evidence add --kind compile_receipt --from compile.json \
    --tool local-demo --command "echo compile ok"
证据已登记：compile_receipt-20261007111012-359ffb
  校验：通过 — 终态成功（SUCCESS）
  来源：local-demo / echo compile ok

$ py -3 .rtd/engine/rtd.py status
对象：{}
阶段：discover
本阶段门控已齐；可以 advance 到下一阶段
证据条数：1；状态版本：2
```

三处值得注意：`setup` 遇到没配执行器时**报缺口并停**，不猜；`evidence add` 会当场校验这条回执
（状态字段必须是终态成功）并给出证据 ID；`status` 把"当前阶段 + 本阶段门控齐没齐"一次说清。

设计来源是 [plan.md](./plan.md)（脱敏版）。未脱敏原稿 `plan.raw.md` 带真实名称与替换对照表，**只在本地**，已在 `.gitignore` 里排除，别外发。

## License

Apache License 2.0。见 `LICENSE` 与 `NOTICE`。

第三方名称与商标的边界写在 `docs/third-party-dependencies.md`：
本仓库不包含任何第三方二进制，文档里提到的组件名只用于说明兼容对象与实测事实，
不表示赞助、背书或关联。
